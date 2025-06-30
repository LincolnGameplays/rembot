from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from llama_cpp import Llama
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RemBOT LLM API",
    description="API for serving the MythoMist-7B GGUF model for RemBOT",
    version="1.0.0",
)

llm_instance: Llama = None

class TextGenerationRequest(BaseModel):
    prompt: str
    max_tokens: int = 500
    temperature: float = 0.7
    top_p: float = 0.9
    stop: list[str] = []
    # Add more generation parameters as needed (e.g., repetition_penalty, top_k)

@app.on_event("startup")
async def startup_event():
    global llm_instance
    model_filename = os.getenv("LLM_MODEL_FILENAME")
    model_path = os.path.join("/app/models", model_filename)
    n_threads = int(os.getenv("LLM_N_THREADS", "4"))
    n_ctx = int(os.getenv("LLM_N_CTX", "4096"))

    if not os.path.exists(model_path):
        logger.error(f"LLM model file not found at {model_path}. Please ensure it's downloaded and mounted.")
        raise RuntimeError(f"LLM model file not found: {model_path}")

    logger.info(f"Attempting to load LLM model: {model_path}")
    logger.info(f"Config: n_threads={n_threads}, n_ctx={n_ctx}")
    try:
        llm_instance = Llama(
            model_path=model_path,
            n_threads=n_threads,
            n_ctx=n_ctx,
            n_gpu_layers=0,  # Explicitly set to 0 for CPU-only inference
            verbose=True,    # Enable verbose logging from llama.cpp
            # Add other parameters for optimization if needed, e.g., n_batch, f16_kv
        )
        logger.info("LLM model loaded successfully.")
    except Exception as e:
        logger.critical(f"Failed to load LLM model. Check model file and parameters: {e}")
        # Exit the application if the model cannot be loaded, as it's a core dependency
        raise SystemExit(f"Failed to load LLM model: {e}")

@app.post("/generate")
async def generate_text(request: TextGenerationRequest):
    if llm_instance is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM model is not loaded or failed to initialize."
        )

    try:
        # Log the prompt for debugging/monitoring
        logger.debug(f"Received prompt for generation: {request.prompt[:200]}...")
        
        output = llm_instance(
            prompt=request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            stop=request.stop,
            echo=False, # Do not echo the prompt in the output
        )
        generated_text = output["choices"][0]["text"].strip()
        logger.debug(f"Generated text: {generated_text[:200]}...")
        return {"text": generated_text}
    except Exception as e:
        logger.error(f"Error during text generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate text: {e}"
        )

@app.get("/health")
async def health_check():
    if llm_instance is not None:
        return {"status": "healthy", "model_loaded": True, "model_path": os.getenv("LLM_MODEL_FILENAME")}
    return {"status": "unhealthy", "model_loaded": False}