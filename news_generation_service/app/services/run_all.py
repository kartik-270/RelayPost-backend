import os
import sys

# Throttle CPU usage for the background jobs
if hasattr(os, 'nice'):
    os.nice(19)
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

try:
    import cloudinary
    if os.environ.get("CLOUDINARY_CLOUD_NAME"):
        cloudinary.config(
            cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
            api_key=os.environ.get("CLOUDINARY_API_KEY"),
            api_secret=os.environ.get("CLOUDINARY_API_SECRET")
        )
except Exception:
    pass

from app.services.ingestion import process_and_store_articles, trim_memory
from app.services.processing import update_article_clusters, generate_ai_summaries
from app.services.cache import update_top_news_cache

if __name__ == "__main__":
    try:
        print("Starting isolated ingestion and processing pipeline...", flush=True)
        process_and_store_articles(page=1, page_size=10)
        trim_memory()

        update_article_clusters()
        trim_memory()

        generate_ai_summaries()
        trim_memory()

        update_top_news_cache()
        trim_memory()

        print("Pipeline completed successfully.", flush=True)
    except Exception as e:
        import traceback
        print(f"Pipeline error: {e}", flush=True)
        traceback.print_exc()
    finally:
        # Force exit to kill any hanging gRPC/OpenMP background threads
        os._exit(0)
