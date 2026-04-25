from google import genai
from config import GCP_PROJECT, GCP_REGION, GEMINI_MODEL

client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_REGION)
resp = client.models.generate_content(
    model=GEMINI_MODEL,
    contents="Say hello in one short sentence.",
)
print(resp.text)