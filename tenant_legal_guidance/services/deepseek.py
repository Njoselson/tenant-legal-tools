import json
import logging
import re
from typing import Dict, List

import aiohttp
import ssl


class DeepSeekClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com/v1"
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Initialized DeepSeekClient")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # Create SSL context for all requests
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = True
        self.ssl_context.verify_mode = ssl.CERT_REQUIRED

    async def chat_completion(self, prompt: str) -> str:
        """Generate a response to a chat prompt using the DeepSeek API."""
        try:
            # Construct the API request payload
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a legal expert assisting with tenant rights and housing law.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,  # Set to 0 for deterministic, grounded responses
            }

            # Make the API request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                    ssl=self.ssl_context
                ) as response:
                    response.raise_for_status()
                    response_data = await response.json()

                    if "choices" in response_data and len(response_data["choices"]) > 0:
                        content = response_data["choices"][0].get("message", {}).get("content", "")
                        return content.strip()
                    else:
                        raise ValueError("Invalid response format from API")

        except Exception as e:
            self.logger.error(f"Error in chat completion: {str(e)}")
            raise

    async def extract_legal_concepts(self, text: str) -> Dict:
        """Use DeepSeek to extract legal concepts from text"""
        self.logger.info("Extracting legal concepts from text")
        self.logger.debug(f"Text length: {len(text)} characters")

        prompt = f"""
        Analyze this legal text and extract:
        1. Relevant housing laws/regulations
        2. Required evidence for claims
        3. Potential remedies
        4. Key legal concepts
        
        Return ONLY the JSON object (no markdown formatting) with these keys: laws, evidence, remedies, concepts.
        
        Text: {text}
        """

        try:
            # Get LLM response
            response = await self.chat_completion(prompt)

            # Clean the content before parsing
            cleaned_content = self._clean_llm_json_output(response)
            self.logger.debug(f"Cleaned Content for JSON parsing: {cleaned_content[:500]}...")

            result = json.loads(cleaned_content)

            self.logger.info("Successfully extracted legal concepts")
            self.logger.debug(
                f"Extracted {len(result.get('laws', []))} laws, {len(result.get('evidence', []))} evidence items"
            )
            return result

        except Exception as e:
            self.logger.error(f"Error extracting legal concepts: {e}", exc_info=True)
            raise

    async def summarize_clinic_notes(self, notes: str) -> Dict:
        """Generate structured summary of legal clinic notes"""
        self.logger.info("Summarizing clinic notes")
        self.logger.debug(f"Notes length: {len(notes)} characters")

        prompt = f"""
        Analyze these legal clinic notes and create a structured summary focusing on:
        1. Consultation Recap: Key facts and issues discussed.
        2. Action Items: Concrete next steps for the tenant.
        
        Return ONLY the JSON object (no markdown formatting) with top-level keys: "consultation_recap" and "action_items".
        - "consultation_recap" should be a dictionary containing:
            - "key_facts": List of strings summarizing important factual points.
            - "legal_issues_identified": List of strings summarizing the legal problems discussed.
        - "action_items" should be a list of strings describing specific, actionable next steps for the tenant.
        
        Notes: {notes}
        """

        try:
            # Get LLM response
            response = await self.chat_completion(prompt)

            # Clean the content before parsing
            cleaned_content = self._clean_llm_json_output(response)
            self.logger.debug(f"Cleaned Content for JSON parsing: {cleaned_content[:500]}...")

            result = json.loads(cleaned_content)

            self.logger.info("Successfully summarized clinic notes")
            self.logger.debug(f"Generated summary with keys: {list(result.keys())}")
            return result

        except Exception as e:
            self.logger.error(f"Error during note summarization: {e}", exc_info=True)
            raise

    async def extract_dates(self, text: str) -> List[Dict]:
        """Extract dates and their context from text"""
        self.logger.info("Extracting dates from text")
        self.logger.debug(f"Text length: {len(text)} characters")

        prompt = f"""
        Extract all dates and their context from this text.
        Return ONLY a JSON array (no markdown formatting) of objects with keys: "date", "context".
        Each object should contain:
        - date: The extracted date (standard format if possible, e.g., YYYY-MM-DD).
        - context: The sentence or phrase containing the date.
        
        Text: {text}
        """

        try:
            # Get LLM response
            response = await self.chat_completion(prompt)

            # Clean the content before parsing
            cleaned_content = self._clean_llm_json_output(response)
            self.logger.debug(f"Cleaned Content for JSON parsing: {cleaned_content[:500]}...")

            result = json.loads(cleaned_content)

            self.logger.info("Successfully extracted dates")
            self.logger.debug(f"Extracted {len(result)} date entries")
            return result

        except Exception as e:
            self.logger.error(f"Error during date extraction: {e}", exc_info=True)
            raise

    def _clean_llm_json_output(self, content_text: str) -> str:
        """Cleans the LLM output string to extract the JSON object or array part."""
        self.logger.debug(f"Attempting to clean content: {content_text[:200]}...")

        # Try extracting JSON object or array from ```json ... ``` block (greedy match)
        # Match {...} or [...] possibly wrapped in markdown fences
        match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", content_text, re.DOTALL | re.S)
        if match:
            json_string = match.group(1)
            self.logger.debug("Extracted JSON using regex from code block")
        else:
            # Fallback: Find the first '{' or '[' and the last '}' or ']'
            start_obj = content_text.find("{")
            end_obj = content_text.rfind("}")
            start_arr = content_text.find("[")
            end_arr = content_text.rfind("]")

            # Determine if it looks more like an object or an array based on first character
            if start_obj != -1 and (start_arr == -1 or start_obj < start_arr):
                # Looks like an object
                if end_obj != -1 and end_obj > start_obj:
                    json_string = content_text[start_obj : end_obj + 1]
                    self.logger.debug("Extracted JSON object using find/rfind method")
                else:
                    json_string = None  # Invalid object structure found
            elif start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
                # Looks like an array
                if end_arr != -1 and end_arr > start_arr:
                    json_string = content_text[start_arr : end_arr + 1]
                    self.logger.debug("Extracted JSON array using find/rfind method")
                else:
                    json_string = None  # Invalid array structure found
            else:
                json_string = None  # Neither object nor array start found

            if json_string is None:
                self.logger.warning(
                    "Could not reliably extract JSON object or array, returning original content string."
                )
                json_string = content_text

        cleaned_string = json_string.strip()
        self.logger.debug(f"Returning cleaned string: {cleaned_string[:200]}...")
        return cleaned_string 