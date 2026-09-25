import os
import requests
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("gmap_scraper.whatsapp")

class MetaWhatsAppService:
    """
    Abstraction for Meta WhatsApp Cloud API.
    Currently rejects sending messages if configuration is missing,
    as required by the safety guidelines.
    """

    def __init__(self):
        # We load these from the environment, though they might be empty.
        self.access_token = os.environ.get("META_ACCESS_TOKEN")
        self.phone_number_id = os.environ.get("META_PHONE_NUMBER_ID")
        self.waba_id = os.environ.get("META_WABA_ID")
        self.app_id = os.environ.get("META_APP_ID")
        # Reason from the most recent failed media upload, so callers can
        # report it instead of a generic failure.
        self.last_media_error = None
        self.api_version = os.environ.get("META_API_VERSION", "v21.0")

    def _redact(self, text: str) -> str:
        """Strip the access token out of any string before it is logged or returned."""
        if text and self.access_token:
            return text.replace(self.access_token, "***")
        return text

    def is_configured(self) -> bool:
        """
        Check if the required Meta API credentials are present in the environment.
        """
        return bool(self.access_token and self.phone_number_id)

    def send_template_message(
        self,
        to_phone: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[list] = None
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Sends a template message via Meta API.

        Returns:
            (success, provider_message_id, provider_status_code, error_reason, provider_error_code)
        """
        if os.environ.get("MOCK_WHATSAPP_API", "false").lower() == "true":
            import uuid
            if "500" in to_phone:
                return False, None, "500", "Simulated 500 error", None
            if "429" in to_phone:
                return False, None, "429", "Simulated 429 rate limit", None
            if "000000000" in to_phone:
                return False, None, None, "Simulated timeout", None

            # Simulate a successful send
            return True, f"mock_wamid.{uuid.uuid4().hex}", "200", None, None

        if not self.is_configured():
            return False, None, None, "Configuration missing: WhatsApp Meta API is not configured.", None

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        # Strip '+' from phone for Meta API which requires e.g., '919911844469'
        formatted_phone = to_phone.lstrip('+')

        payload = {
            "messaging_product": "whatsapp",
            "to": formatted_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code
                }
            }
        }

        if components:
            payload["template"]["components"] = components

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response_data = response.json()

            if response.status_code in (200, 201):
                message_id = response_data.get("messages", [{}])[0].get("id")
                return True, message_id, str(response.status_code), None, None

            err = response_data.get("error", {}) or {}
            error_msg = self._redact(err.get("message", "Unknown Meta API Error"))
            # Meta puts the actionable numeric code in error.code, with extra
            # detail in error_data.details. Keep both, they are not secrets.
            error_code = err.get("code")
            details = (err.get("error_data") or {}).get("details")
            if details:
                error_msg = f"{error_msg} ({self._redact(str(details))})"
            error_code = str(error_code) if error_code is not None else None

            logger.error(
                f"Meta API Error status={response.status_code} code={error_code} msg={error_msg}"
            )
            return False, None, str(response.status_code), f"Meta API rejection: {error_msg}", error_code

        except requests.exceptions.Timeout:
            return False, None, None, "Network timeout", None
        except Exception as e:
            logger.exception("Failed to send WhatsApp message")
            return False, None, None, f"Provider error: {self._redact(str(e))}", None

    def upload_media(self, file_path: str, media_type: str) -> Optional[str]:
        """
        Uploads media to Meta and returns the Meta media ID.
        """
        import os, uuid
        if os.environ.get("MOCK_WHATSAPP_API", "false").lower() == "true":
            # Simulate a successful media upload
            return f"mock_media_{uuid.uuid4().hex}"

        if not self.is_configured():
            logger.error("Meta API not configured for media upload")
            return None

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/media"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        # We need to map media_type (e.g. "image", "video") to a proper mime type
        # or rely on python-requests to guess from extension.
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        try:
            with open(file_path, "rb") as f:
                files = {
                    "file": (os.path.basename(file_path), f, mime_type)
                }
                data = {
                    "messaging_product": "whatsapp"
                }
                response = requests.post(url, headers=headers, data=data, files=files, timeout=30)

            if response.status_code in (200, 201):
                self.last_media_error = None
                return response.json().get("id")

            try:
                err = (response.json().get("error") or {})
                detail = (err.get("error_data") or {}).get("details") or err.get("message")
            except ValueError:
                detail = f"HTTP {response.status_code}"
            self.last_media_error = self._redact(str(detail))
            logger.error(
                f"Meta Media Upload Error {response.status_code}: {self.last_media_error}"
            )
            return None

        except Exception as e:
            self.last_media_error = self._redact(str(e))
            logger.exception("Failed to upload media to Meta")
            return None

    def list_message_templates(self) -> Dict[str, Any]:
        """
        Fetches the templates registered in the Meta WhatsApp Business Account.

        Meta resolves a template send by (name, language) against APPROVED
        templates in the WABA. A locally-created template that was never
        submitted to Meta does not exist as far as sending is concerned, which
        is what produces error #132001 at send time.

        Returns {"status": "success", "templates": [...]} or
                {"status": "failed", "error": "..."}.
        """
        if os.environ.get("MOCK_WHATSAPP_API", "false").lower() == "true":
            return {
                "status": "success",
                "templates": [
                    {"name": "hello_world", "language": "en_US",
                     "status": "APPROVED", "category": "UTILITY"}
                ],
            }

        if not self.access_token:
            return {"status": "failed", "error": "WhatsApp Meta credentials are not configured"}
        if not self.waba_id:
            return {
                "status": "failed",
                "error": "META_WABA_ID is not configured. It is required to read approved templates.",
            }

        url = f"https://graph.facebook.com/{self.api_version}/{self.waba_id}/message_templates"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        templates = []
        params = {"limit": 100, "fields": "name,language,status,category"}
        try:
            # Meta paginates; follow "next" so a large WABA is fully covered.
            while url:
                response = requests.get(url, headers=headers, params=params, timeout=15)
                if response.status_code != 200:
                    try:
                        error_msg = response.json().get("error", {}).get("message", "Unknown Meta API Error")
                    except ValueError:
                        error_msg = f"HTTP {response.status_code}"
                    error_msg = self._redact(error_msg)
                    logger.error(f"Meta template listing failed: {error_msg}")
                    return {"status": "failed", "error": f"Meta API rejection: {error_msg}"}

                data = response.json()
                templates.extend(data.get("data", []))
                url = (data.get("paging") or {}).get("next")
                params = None  # "next" already carries the query string

            return {"status": "success", "templates": templates}

        except requests.exceptions.Timeout:
            return {"status": "failed", "error": "Network timeout while contacting Meta API"}
        except Exception as e:
            logger.exception("Failed to list Meta templates")
            return {"status": "failed", "error": f"Provider error: {self._redact(str(e))}"}

    def find_template_id(self, name: str, language_code: str) -> Optional[str]:
        """
        Meta's own id for a template, needed to edit it. Templates are addressed
        by id for writes even though sends address them by name.
        """
        listing = self.list_message_templates()
        if listing["status"] != "success":
            return None
        for t in listing["templates"]:
            if t.get("name") == name and t.get("language") == language_code:
                return t.get("id")
        return None

    def update_message_template(self, meta_template_id: str, components: list,
                                category: str = None) -> Dict[str, Any]:
        """
        Pushes edited content to an existing Meta template.

        A template's text lives with Meta: a send only supplies the name and
        parameters, and Meta renders the message from its own stored copy. So
        editing locally changes nothing about what recipients actually receive
        until the change is sent here.
        """
        if os.environ.get("MOCK_WHATSAPP_API", "false").lower() == "true":
            return {"status": "success", "template_status": "PENDING"}

        if not self.access_token:
            return {"status": "failed", "error": "WhatsApp Meta credentials are not configured"}

        payload = {"components": components}
        if category:
            payload["category"] = category.upper()

        try:
            r = requests.post(
                f"https://graph.facebook.com/{self.api_version}/{meta_template_id}",
                headers={"Authorization": f"Bearer {self.access_token}",
                         "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            data = r.json()
            if r.status_code in (200, 201) and data.get("success", True):
                return {"status": "success", "template_status": "PENDING"}

            err = data.get("error", {}) or {}
            user_title = err.get("error_user_title")
            user_msg = err.get("error_user_msg")
            msg = f"{user_title}: {user_msg}" if (user_title and user_msg) else (
                user_msg or err.get("message", f"HTTP {r.status_code}"))
            msg = self._redact(str(msg))
            logger.error(f"Meta template edit failed code={err.get('code')} msg={msg}")
            return {"status": "failed", "error": msg,
                    "error_code": str(err.get("code")) if err.get("code") is not None else None}

        except requests.exceptions.Timeout:
            return {"status": "failed", "error": "Network timeout while updating the template"}
        except Exception as e:
            logger.exception("Template edit failed")
            return {"status": "failed", "error": f"Provider error: {self._redact(str(e))}"}

    def find_approved_template(self, name: str, language_code: str) -> Dict[str, Any]:
        """
        Pre-flight check used before a campaign sends anything.

        Returns {"ok": True} when an APPROVED template matches, otherwise
        {"ok": False, "error": "...", "available": [...]} so the caller can
        fail the campaign with an actionable reason instead of burning real
        sends against Meta.
        """
        listing = self.list_message_templates()
        if listing["status"] != "success":
            return {"ok": False, "error": listing["error"], "available": []}

        available = [
            f"{t.get('name')} ({t.get('language')})"
            for t in listing["templates"]
            if t.get("status") == "APPROVED"
        ]

        for t in listing["templates"]:
            if t.get("name") == name and t.get("language") == language_code:
                if t.get("status") != "APPROVED":
                    return {
                        "ok": False,
                        "error": (
                            f"Template '{name}' ({language_code}) exists in Meta but its "
                            f"status is {t.get('status')}, not APPROVED."
                        ),
                        "available": available,
                    }
                return {"ok": True, "error": None, "available": available}

        return {
            "ok": False,
            "error": (
                f"Template '{name}' with language '{language_code}' is not an approved "
                f"template in this WhatsApp Business Account."
            ),
            "available": available,
        }

    def _resolve_app_id(self) -> Optional[str]:
        """
        The resumable upload endpoint is app-scoped. Prefer the configured
        META_APP_ID, else ask Meta which app this token belongs to.
        """
        if self.app_id:
            return self.app_id
        try:
            r = requests.get(
                f"https://graph.facebook.com/{self.api_version}/debug_token",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params={"input_token": self.access_token},
                timeout=15,
            )
            if r.status_code == 200:
                self.app_id = (r.json().get("data") or {}).get("app_id")
                return self.app_id
        except Exception:
            logger.exception("Could not resolve Meta app id")
        return None

    def upload_resumable(self, file_path: str) -> Dict[str, Any]:
        """
        Uploads a file through Meta's Resumable Upload API and returns the
        opaque handle used as a template's example header media.

        This is a different mechanism from upload_media(): that one returns a
        media ID for *sending*, while template creation requires a handle.

        Returns {"status": "success", "handle": "..."} or
                {"status": "failed", "error": "..."}.
        """
        if os.environ.get("MOCK_WHATSAPP_API", "false").lower() == "true":
            return {"status": "success", "handle": "mock_handle_4::aW1hZ2U="}

        if not self.access_token:
            return {"status": "failed", "error": "WhatsApp Meta credentials are not configured"}

        app_id = self._resolve_app_id()
        if not app_id:
            return {"status": "failed", "error": "Could not determine the Meta app id for the upload"}

        if not os.path.exists(file_path):
            return {"status": "failed", "error": f"Local media file not found: {os.path.basename(file_path)}"}

        import mimetypes
        file_length = os.path.getsize(file_path)
        file_type, _ = mimetypes.guess_type(file_path)
        if not file_type:
            file_type = "application/octet-stream"

        try:
            # Step 1 - open an upload session.
            start = requests.post(
                f"https://graph.facebook.com/{self.api_version}/{app_id}/uploads",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params={"file_length": file_length, "file_type": file_type},
                timeout=30,
            )
            if start.status_code not in (200, 201):
                msg = self._redact(start.json().get("error", {}).get("message", f"HTTP {start.status_code}"))
                return {"status": "failed", "error": f"Upload session failed: {msg}"}

            session_id = start.json().get("id")
            if not session_id:
                return {"status": "failed", "error": "Meta did not return an upload session id"}

            # Step 2 - send the bytes. This endpoint wants the OAuth scheme.
            with open(file_path, "rb") as fh:
                payload = fh.read()

            finish = requests.post(
                f"https://graph.facebook.com/{self.api_version}/{session_id}",
                headers={
                    "Authorization": f"OAuth {self.access_token}",
                    "file_offset": "0",
                    "Content-Type": "application/octet-stream",
                },
                data=payload,
                timeout=120,
            )
            if finish.status_code not in (200, 201):
                msg = self._redact(finish.json().get("error", {}).get("message", f"HTTP {finish.status_code}"))
                return {"status": "failed", "error": f"Upload failed: {msg}"}

            handle = finish.json().get("h")
            if not handle:
                return {"status": "failed", "error": "Meta did not return an upload handle"}
            return {"status": "success", "handle": handle}

        except requests.exceptions.Timeout:
            return {"status": "failed", "error": "Network timeout during media upload"}
        except Exception as e:
            logger.exception("Resumable upload failed")
            return {"status": "failed", "error": f"Provider error: {self._redact(str(e))}"}

    def create_message_template(self, name: str, language: str, category: str,
                                components: list) -> Dict[str, Any]:
        """
        Submits a template to the WABA for review.

        Returns {"status": "success", "id": ..., "template_status": ...} or
                {"status": "failed", "error": ..., "error_code": ...}.
        """
        if os.environ.get("MOCK_WHATSAPP_API", "false").lower() == "true":
            return {"status": "success", "id": "mock_template_id", "template_status": "PENDING"}

        if not self.access_token:
            return {"status": "failed", "error": "WhatsApp Meta credentials are not configured"}
        if not self.waba_id:
            return {"status": "failed", "error": "META_WABA_ID is not configured"}

        try:
            r = requests.post(
                f"https://graph.facebook.com/{self.api_version}/{self.waba_id}/message_templates",
                headers={"Authorization": f"Bearer {self.access_token}",
                         "Content-Type": "application/json"},
                json={"name": name, "language": language,
                      "category": category, "components": components},
                timeout=30,
            )
            data = r.json()
            if r.status_code in (200, 201):
                return {"status": "success", "id": data.get("id"),
                        "template_status": data.get("status", "PENDING")}

            err = data.get("error", {}) or {}
            # Meta's generic "message" is usually just "Invalid parameter"; the
            # actionable text lives in error_user_title / error_user_msg, so
            # prefer those and fall back to the generic one.
            user_title = err.get("error_user_title")
            user_msg = err.get("error_user_msg")
            if user_msg:
                msg = f"{user_title}: {user_msg}" if user_title else user_msg
            else:
                msg = err.get("message", f"HTTP {r.status_code}")
                details = (err.get("error_data") or {}).get("details")
                if details:
                    msg = f"{msg} ({details})"
            msg = self._redact(str(msg))

            logger.error(
                f"Meta template submission failed code={err.get('code')} "
                f"subcode={err.get('error_subcode')} msg={msg}"
            )
            return {"status": "failed", "error": msg,
                    "error_code": str(err.get("code")) if err.get("code") is not None else None,
                    "error_subcode": err.get("error_subcode")}

        except requests.exceptions.Timeout:
            return {"status": "failed", "error": "Network timeout while submitting the template"}
        except Exception as e:
            logger.exception("Template submission failed")
            return {"status": "failed", "error": f"Provider error: {self._redact(str(e))}"}

    def verify_connection(self) -> Dict[str, Any]:
        """
        Verifies the Meta API connection using the configured access token and phone number ID.
        Returns a dict with 'status' ('success' or 'failed') and related data or error message.
        """
        if os.environ.get("MOCK_WHATSAPP_API", "false").lower() == "true":
            # Simulate a successful connection for testing
            return {
                "status": "success",
                "verified_name": "Mock Business Account",
                "display_phone_number": "+1 555-0198"
            }

        if not self.is_configured():
            return {
                "status": "failed",
                "error": "WhatsApp Meta credentials are not configured"
            }

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        try:
            # We use a short timeout because this is an interactive check
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "success",
                    "verified_name": data.get("verified_name"),
                    "display_phone_number": data.get("display_phone_number")
                }
            else:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "Unknown Meta API Error")
                except ValueError:
                    error_msg = f"HTTP {response.status_code}"

                # Sanitize error to ensure we never leak token
                error_msg = error_msg.replace(self.access_token, "***")
                logger.error(f"Meta Connection Check Failed: {error_msg}")

                return {
                    "status": "failed",
                    "error": f"Meta API rejection: {error_msg}"
                }

        except requests.exceptions.Timeout:
            return {
                "status": "failed",
                "error": "Network timeout while contacting Meta API"
            }
        except Exception as e:
            error_str = str(e).replace(self.access_token, "***")
            logger.exception("Failed to verify Meta connection")
            return {
                "status": "failed",
                "error": f"Provider error: {error_str}"
            }
