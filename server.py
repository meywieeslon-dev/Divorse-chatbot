from fastapi import FastAPI
from pydantic import BaseModel

from graph import divorce_graph, _get_content

app = FastAPI()


class ChatRequest(BaseModel):
    message: str
    thread_id: str
    auth_key: str


class ChatResponse(BaseModel):
    answer: str


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    result_state = divorce_graph.invoke(
        {
            "messages": [{"role": "user", "content": request.message}],
            "auth_key": request.auth_key,
        },
        config={"configurable": {"thread_id": request.thread_id}},
    )
    answer = _get_content(result_state["messages"][-1])
    return ChatResponse(answer=answer)