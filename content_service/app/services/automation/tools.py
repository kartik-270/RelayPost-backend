import os
import google.generativeai as genai
from tavily import TavilyClient
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from typing import List, Optional
import json

# --- Tavily Tool ---
class TavilyTool:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
        if self.api_key:
            self.client = TavilyClient(api_key=self.api_key)
        else:
            self.client = None

    async def search(self, query: str, topic: str = "news", max_results: int = 5):
        if not self.client:
            print("Tavily API key missing. Skipping search.")
            return []
        
        try:
            response = self.client.search(
                query=query,
                topic=topic,
                search_depth="basic",
                max_results=max_results
            )
            return response.get("results", [])
        except Exception as e:
            print(f"Tavily Search Error: {e}")
            return []

    async def extract(self, urls: List[str]):
        if not self.client:
            return []
        try:
            # Note: Tavily SDK might have extract or we use search with include_content=True
            # For simplicity, we'll assume the search results already have enough content 
            # or we can use the extract client if available in the SDK version.
            return self.client.extract(urls=urls)
        except Exception as e:
            print(f"Tavily Extract Error: {e}")
            return []

# --- Gemini Tool ---
class GeminiTool:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemma-4-31b-it")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            print(f"[GEMINI] Selected model: {self.model_name}")
            self.model = genai.GenerativeModel(self.model_name)
        else:
            self.model = None

    async def generate_structured(self, prompt: str, temperature: float = 0.7, top_p: float = 0.95, max_retries: int = 4):
        import asyncio
        if not self.model:
            raise Exception("Gemini API key missing")
        
        for attempt in range(max_retries):
            if attempt == 0:
                generation_config = {
                    "temperature": temperature,
                    "top_p": top_p,
                    "response_mime_type": "application/json",
                }
            elif attempt == 1:
                print("[GEMINI] Retrying: Falling back to text/plain mode...")
                generation_config = {
                    "temperature": temperature,
                    "top_p": top_p,
                }
            elif attempt == 2:
                print("[GEMINI] Retrying: Dropping temperature and top_p but keeping json mode...")
                generation_config = {
                    "response_mime_type": "application/json",
                }
            else:
                print("[GEMINI] Retrying: Dropping all generation_config parameters...")
                generation_config = None
                
            try:
                if generation_config is not None:
                    response = await self.model.generate_content_async(prompt, generation_config=generation_config)
                else:
                    response = await self.model.generate_content_async(prompt)
                text = response.text
                
                # Use raw_decode loop to extract all valid JSON objects/arrays
                import json
                decoder = json.JSONDecoder()
                pos = 0
                parsed_objects = []
                while pos < len(text):
                    start_obj = text.find('{', pos)
                    start_arr = text.find('[', pos)
                    
                    start = -1
                    if start_obj != -1 and start_arr != -1:
                        start = min(start_obj, start_arr)
                    elif start_obj != -1:
                        start = start_obj
                    elif start_arr != -1:
                        start = start_arr
                        
                    if start == -1:
                        break
                        
                    try:
                        obj, end_pos = decoder.raw_decode(text[start:])
                        parsed_objects.append(obj)
                        pos = start + end_pos
                    except json.JSONDecodeError:
                        pos = start + 1
                
                if parsed_objects:
                    # Normalize lists containing a single dict or other list
                    normalized_objects = []
                    for obj in parsed_objects:
                        curr = obj
                        while isinstance(curr, list) and len(curr) == 1:
                            curr = curr[0]
                        normalized_objects.append(curr)
                    
                    # Also include any dicts nested within top-level lists
                    extended_objects = []
                    for obj in normalized_objects:
                        extended_objects.append(obj)
                        if isinstance(obj, list):
                            for item in obj:
                                if isinstance(item, dict):
                                    extended_objects.append(item)

                    # Filter and prioritize the object matching our expected schema
                    for obj in reversed(extended_objects):
                        if isinstance(obj, dict):
                            if "topics" in obj and isinstance(obj["topics"], list) and len(obj["topics"]) > 0:
                                return obj
                            if "content_blocks" in obj and isinstance(obj["content_blocks"], list) and len(obj["content_blocks"]) > 0:
                                return obj
                            if "focus_keyword" in obj or "meta_title" in obj:
                                return obj
                                
                    # Fallback to the last parsed dict/list (usually the final generated JSON)
                    for obj in reversed(extended_objects):
                        if isinstance(obj, (dict, list)):
                            return obj
                            
                # Fallback to direct loads if no objects were parsed
                parsed = json.loads(text)
                while isinstance(parsed, list) and len(parsed) == 1:
                    parsed = parsed[0]
                return parsed
            except Exception as e:
                error_msg = str(e)
                print(f"Gemini Generation Attempt {attempt + 1} Failed: {error_msg[:200]}")
                if attempt < max_retries - 1:
                    is_rate_limit = "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg
                    is_server_error = "500" in error_msg or "503" in error_msg or "InternalServerError" in error_msg or "ServiceUnavailable" in error_msg
                    
                    if is_rate_limit:
                        import re
                        match = (
                            re.search(r'Please retry in (\d+)', error_msg) or
                            re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', error_msg)
                        )
                        wait_time = int(match.group(1)) + 5 if match else 30 * (attempt + 1)
                        print(f"Rate limited. Retrying in {wait_time} seconds...")
                    elif is_server_error:
                        wait_time = 5 * (attempt + 1)
                        print(f"Server error. Retrying in {wait_time} seconds...")
                    else:
                        wait_time = 2 * (attempt + 1)
                        print(f"Transient error. Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    raise e

# --- Email Tool ---
class EmailTool:
    def __init__(self):
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        use_starttls = smtp_port == 587
        use_ssl = smtp_port == 465
        self.conf = ConnectionConfig(
            MAIL_USERNAME=os.getenv("SMTP_USERNAME"),
            MAIL_PASSWORD=os.getenv("SMTP_PASSWORD"),
            MAIL_FROM=os.getenv("SMTP_FROM", os.getenv("SMTP_USERNAME", "no-reply@relaypost.me")),
            MAIL_PORT=smtp_port,
            MAIL_SERVER=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
            MAIL_FROM_NAME=os.getenv("SMTP_FROM_NAME", "RelayPost"),
            MAIL_STARTTLS=use_starttls,
            MAIL_SSL_TLS=use_ssl,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True
        )

    async def send_notification(self, recipients: List[str], subject: str, body_html: str):
        if not self.conf.MAIL_PASSWORD:
            print("SMTP_PASSWORD missing. Skipping email notification.")
            return False
            
        message = MessageSchema(
            subject=subject,
            recipients=recipients,
            body=body_html,
            subtype=MessageType.html
        )
        
        fm = FastMail(self.conf)
        try:
            await fm.send_message(message)
            return True
        except Exception as e:
            print(f"Email Notification Error: {e}")
            return False
# --- Unsplash Tool ---
class UnsplashTool:
    def __init__(self):
        self.access_key = os.getenv("UNSPLASH_ACCESS_KEY")
        self.base_url = "https://api.unsplash.com"

    async def search_image(self, query: str, orientation: str = "landscape") -> Optional[str]:
        if not self.access_key:
            print("UNSPLASH_ACCESS_KEY missing. Skipping image search.")
            return None
            
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/search/photos",
                    params={
                        "query": query,
                        "per_page": 1,
                        "orientation": orientation
                    },
                    headers={"Authorization": f"Client-ID {self.access_key}"},
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    if results:
                        # Return the regular size URL with high quality params
                        return results[0]["urls"]["regular"] + "&auto=format&fit=crop&w=1200&q=80"
                else:
                    print(f"Unsplash API Error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Unsplash Tool Error: {e}")
            
        return None
    async def download_image(self, url: str) -> Optional[bytes]:
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=20.0, follow_redirects=True)
                if response.status_code == 200:
                    return response.content
                else:
                    print(f"Failed to download image: {response.status_code}")
        except Exception as e:
            print(f"Image Download Error: {e}")
            
        return None
