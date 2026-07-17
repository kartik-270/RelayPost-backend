import os
import sys

# Throttle CPU usage for the background ML jobs
if hasattr(os, 'nice'):
    os.nice(19)
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
try:
    import torch
    torch.set_num_threads(1)
except ImportError:
    pass

from app.services.ingestion import process_and_store_articles
from app.services.processing import update_article_clusters, generate_ai_summaries
from app.services.cache import update_top_news_cache

if __name__ == "__main__":
    try:
        print("Starting isolated ingestion and processing pipeline...", flush=True)
        process_and_store_articles(page=1, page_size=3)
        update_article_clusters()
        generate_ai_summaries()
        update_top_news_cache()
        print("Pipeline completed successfully.", flush=True)
    except Exception as e:
        import traceback
        print(f"Pipeline error: {e}", flush=True)
        traceback.print_exc()
    finally:
        # Force exit to kill any hanging gRPC/OpenMP background threads
        os._exit(0)
