# Decisions

## 1. Fixed routing instead of model-based routing

The orchestrator calls the agents in a fixed order written in Python, rather than letting a model decide which agent to call next. This keeps the flow predictable and easy to debug while learning A2A.

## 2. Local models via Ollama behind one swappable model client

All model calls go through a single model-client module that talks to Ollama on `localhost:11434`. This keeps the project free of paid APIs and means we can swap the model or provider by changing one file.
