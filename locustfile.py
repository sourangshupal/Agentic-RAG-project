"""Locust load test for /api/v1/ask-agentic endpoint.

Usage:
    locust -f locustfile.py --headless -u 10 -r 2 -t 60s

Flags:
    -u 10    = 10 concurrent users
    -r 2     = spawn 2 users per second
    -t 60s   = run for 60 seconds
    --headless = no web UI, CLI output only
"""
from locust import HttpUser, task, between


class RAGApiUser(HttpUser):
    """Simulates a user asking questions to the RAG API."""

    # Target the EKS LoadBalancer URL
    host = "http://ae18980d895d74b308f007e777bc185a-1762723266.us-east-1.elb.amazonaws.com"

    # No wait between requests — maximum throughput
    wait_time = between(0, 0)

    @task(3)
    def ask_agentic_transformer(self):
        """Ask about transformer architecture (most common query)."""
        self.client.post(
            "/api/v1/ask-agentic",
            json={"query": "What is transformer architecture?"},
            headers={"Content-Type": "application/json"},
        )

    @task(2)
    def ask_agentic_attention(self):
        """Ask about attention mechanism."""
        self.client.post(
            "/api/v1/ask-agentic",
            json={"query": "Explain the attention mechanism in deep learning"},
            headers={"Content-Type": "application/json"},
        )

    @task(1)
    def ask_agentic_rl(self):
        """Ask about reinforcement learning."""
        self.client.post(
            "/api/v1/ask-agentic",
            json={"query": "What is policy gradient in reinforcement learning?"},
            headers={"Content-Type": "application/json"},
        )
