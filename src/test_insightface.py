from insightface.app import FaceAnalysis

print("Loading AI model...")

app = FaceAnalysis(
    name="buffalo_s",
    providers=["CPUExecutionProvider"]
)

app.prepare(ctx_id=0, det_size=(640, 640))

print("InsightFace is working! AI model loaded successfully.")