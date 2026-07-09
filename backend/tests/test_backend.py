"""
test_backend.py — Unit and integration tests for the HR Chatbot FastAPI backend.

Run with:
    cd backend
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_backend.py" -v
"""

import sys
import os
import unittest

# Ensure the backend root is on the path so 'app' can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.policies import load_policies, get_policy_document_text


class TestHRPolicyBotBackend(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    # ------------------------------------------------------------------
    # Health endpoint
    # ------------------------------------------------------------------
    def test_health_endpoint_status(self):
        """Health check returns HTTP 200."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_health_endpoint_payload(self):
        """Health check payload has required fields."""
        data = self.client.get("/health").json()
        self.assertIn("status", data)
        self.assertEqual(data["status"], "healthy")
        # Updated field name: 'company' (not 'company_name')
        self.assertIn("company", data)
        self.assertEqual(data["company"], "TechNovance Solutions")
        self.assertIn("api_configured", data)
        self.assertIn("version", data)

    # ------------------------------------------------------------------
    # Policy loading
    # ------------------------------------------------------------------
    def test_load_policies_structure(self):
        """Policies JSON loads and contains all 10 required sections."""
        policies = load_policies()
        self.assertIsInstance(policies, dict)
        required_sections = [
            "company", "leave_policy", "wfh_policy", "attendance_policy",
            "expense_reimbursement", "dress_code", "holiday_list_2025",
            "appraisal_policy", "probation_policy", "notice_period",
            "grievance_policy",
        ]
        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, policies, f"Missing policy section: {section}")

    def test_load_policies_company_info(self):
        """Company metadata is correct."""
        policies = load_policies()
        self.assertEqual(policies["company"]["name"], "TechNovance Solutions Pvt. Ltd.")
        self.assertEqual(policies["company"]["hr_contact"], "hr@technovance.com")

    def test_policy_document_text(self):
        """Formatted policy text contains expected keywords."""
        text = get_policy_document_text()
        self.assertIsInstance(text, str)
        for keyword in ["casual_leave", "wfh_policy", "expense_reimbursement"]:
            with self.subTest(keyword=keyword):
                self.assertIn(keyword, text)

    # ------------------------------------------------------------------
    # Chat endpoint — validation
    # ------------------------------------------------------------------
    def test_chat_endpoint_missing_message(self):
        """Missing 'message' field returns 422 Unprocessable Entity."""
        response = self.client.post("/api/chat", json={"history": []})
        self.assertEqual(response.status_code, 422)

    def test_chat_endpoint_empty_message(self):
        """Empty string 'message' returns 422 (min_length=1)."""
        response = self.client.post("/api/chat", json={"message": "", "history": []})
        self.assertEqual(response.status_code, 422)

    def test_chat_endpoint_invalid_history_role(self):
        """History message with invalid role returns 422."""
        response = self.client.post("/api/chat", json={
            "message": "Hello",
            "history": [{"role": "system", "content": "You are a bot."}],
        })
        self.assertEqual(response.status_code, 422)

    # ------------------------------------------------------------------
    # Chat endpoint — API key guard
    # ------------------------------------------------------------------
    def test_chat_without_api_key_returns_503(self):
        """When the API key is not configured, the endpoint returns 503."""
        original_provider = settings.AI_PROVIDER
        original_gemini = settings.GEMINI_API_KEY
        original_groq = settings.GROQ_API_KEY
        try:
            settings.AI_PROVIDER = "google_genai"
            settings.GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
            settings.GROQ_API_KEY = ""
            response = self.client.post("/api/chat", json={
                "message": "How many casual leaves do I get?",
                "history": [],
            })
            self.assertEqual(response.status_code, 503)
        finally:
            settings.AI_PROVIDER = original_provider
            settings.GEMINI_API_KEY = original_gemini
            settings.GROQ_API_KEY = original_groq

    # ------------------------------------------------------------------
    # Schema validation — history cap
    # ------------------------------------------------------------------
    def test_history_cap_enforced(self):
        """The schema caps history at 20 messages on ingestion."""
        from app.schemas import ChatRequest, ChatMessage
        long_history = [
            ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"msg {i}")
            for i in range(30)
        ]
        req = ChatRequest(message="test", history=long_history)
        self.assertLessEqual(len(req.history), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
