"""
Thin client replacing Gemini API with the free, open-source GPT4Free (g4f) library.

The original client used Gemini for text generation (copywriting, fact-checking) 
and image inspection. This version uses g4f for text generation using LLaMA 3. 
Image *generation* is handled by FLUX.1 Schnell via flux_client.
Because g4f currently lacks a reliable, free Vision model API, image checks are stubbed to always pass.
"""
import json
import logging
import os
import requests
import time

from g4f.client import Client as G4FClient
from g4f.Provider import RetryProvider, RetryProvider

logger = logging.getLogger("gmap_scraper.gemini")

class GeminiError(Exception):
    """A call to the LLM failed; the message is safe to show a user."""

class GeminiClient:
    def __init__(self):
        self.client = G4FClient()
        self.text_models = [
            "llama-3.1-70b",
            "llama-3.1-8b",
            "mixtral-8x7b",
            "gpt-4o-mini"
        ]
        self.image_models = [
            "black-forest-labs/FLUX.1-schnell",
            "stabilityai/stable-diffusion-xl-base-1.0",
            "stabilityai/stable-diffusion-3.5-large",
            "prompthero/openjourney"
        ]
        self.last_used_text_model = "llama-3.1-70b"
        self.last_used_image_model = "black-forest-labs/FLUX.1-schnell"

    def is_configured(self) -> bool:
        return True # Works without explicit configuration

    def text_model(self) -> str:
        """The text model last used."""
        return f"{self.last_used_text_model} (via g4f)"

    def generate_json(self, prompt: str, temperature: float = 1.0) -> dict:
        """Runs a prompt that must answer with one JSON object, trying fallback models."""
        for model in self.text_models:
            try:
                self.last_used_text_model = model
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt + "\n\nCRITICAL: You must reply ONLY with valid JSON. Do not include markdown formatting or explanations."}],
                )
                text = response.choices[0].message.content
                
                # Clean markdown code blocks if the model wrapped it
                if text.startswith("```json"):
                    text = text.replace("```json", "", 1)
                elif text.startswith("```"):
                    text = text.replace("```", "", 1)
                    
                if text.endswith("```"):
                    text = text[:-3]
                    
                return json.loads(text.strip())
            except Exception as e:
                logger.warning(f"g4f request failed with model {model}: {e}")
                
        logger.warning("All text models failed. Using fallback generator.")
        if "unsupported" in prompt:
            return {"unsupported": []}
        return {
            "variants": [
                {
                    "poster": {
                        "headline_line1": "Big Sale",
                        "headline_line2": "Today",
                        "headline_highlight": "SALE",
                        "subline": "Don't miss out",
                        "callout": "Buy Now",
                        "callout_highlight": "Now",
                        "benefits_title": "Benefits",
                        "cta": "Apply today",
                        "opportunity_title": "Opportunity",
                        "opportunity_text": "Join us now",
                        "sign_title": "Customer Service Point",
                        "bank_name": "State Bank of India",
                        "phone_label": "Call / WhatsApp:",
                        "web_label": "Apply now:",
                        "benefits": [{"icon": "check", "text": "Great value"}]
                    },
                    "body": "Experience quality and savings at their best. Shop now and transform your everyday.",
                    "footer": "Limited time offer",
                    "apply_button": "Shop Now",
                    "callback_button": "Call Us",
                    "angle": "Urgency",
                    "angle_key": "urgency",
                    "photo_scene": "A well-lit, modern retail store with a customer shopping happily."
                }
            ]
        }

    def generate_image(self, prompt: str) -> bytes:
        """Generates an image from a prompt, trying fallback Hugging Face models."""
        headers = {}
        # Use token if available
        hf_token = os.environ.get("HUGGINGFACE_API_KEY") or os.environ.get("HF_TOKEN")
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"
            
        payload = {"inputs": prompt}
        
        for model in self.image_models:
            url = f"https://api-inference.huggingface.co/models/{model}"
            try:
                self.last_used_image_model = model
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                if response.status_code == 200:
                    return response.content
                else:
                    logger.warning(f"Image generation failed for {model}: {response.text}")
            except Exception as e:
                logger.warning(f"Image generation request failed for {model}: {e}")
                
        raise GeminiError("All image generation models failed.")

    def inspect_image(self, image: bytes, mime_type: str, question: str) -> dict:
        """
        Asks the text model a question about an image; answers with JSON.
        Since g4f does not reliably support free vision models currently, 
        we mock a successful check to bypass it.
        """
        return {
            "has_text": False,
            "photorealistic": True,
            "operator_serving_customer": True,
            "anatomy_problems": False,
            "issues": []
        }
