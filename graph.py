from typing import Annotated, Optional, TypedDict

from langchain_gigachat.chat_models import GigaChat
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3
import os
import time

class DivorceState(TypedDict):
    messages: Annotated[list, add_messages]
    has_children: Optional[bool]
    has_property: Optional[bool]
    both_agree: Optional[bool]
    auth_key: str
    greeted: bool
    intro_given: bool


def _get_content(message) -> str:
    if isinstance(message, dict):
        return message["content"]
    return message.content


def _get_role(message) -> str:
    if isinstance(message, dict):
        return message["role"]
    return "user" if message.type == "human" else "assistant"


def get_pending_field(state: DivorceState) -> Optional[str]:
    if state.get("has_children") is None:
        return "has_children"
    if state.get("has_property") is None:
        return "has_property"
    if state.get("both_agree") is None:
        return "both_agree"
    return None


_QUESTIONS = {
    "has_children": "У вас с супругом есть общие несовершеннолетние дети?",
    "has_property": "Есть ли совместно нажитое имущество, которое нужно делить?",
    "both_agree": "Оба супруга согласны на развод, или кто-то из вас против?",
}


def greet(state: DivorceState) -> dict:
    text = (
        "Здравствуйте! Я помогу разобраться с общими вопросами о процедуре "
        "развода в РФ. Расскажите, что у вас за ситуация?"
    )
    return {"messages": [{"role": "assistant", "content": text}], "greeted": True}


def entry_router(state: DivorceState) -> str:
    if not state.get("greeted"):
        return "greet"
    return "parse"


def ask_next_question(state: DivorceState) -> dict:
    field = get_pending_field(state)
    if field is None:
        return {}

    auth_key = state["auth_key"]
    last_message = state["messages"][-1] if state["messages"] else None
    last_text = _get_content(last_message) if last_message else ""
    intro_needed = not state.get("intro_given")

    model = GigaChat(
        credentials=auth_key,
        scope="GIGACHAT_API_PERS",
        model="GigaChat-3-Ultra",
        verify_ssl_certs=False,
        timeout=30,
    )

    if intro_needed:
        style_instruction = (
            "Это первый уточняющий вопрос в разговоре — начни с короткой фразы "
            "своими словами в духе «Хорошо, сейчас задам несколько уточняющих "
            "вопросов, чтобы разобраться в ситуации», не копируя пример дословно."
        )
    else:
        style_instruction = (
            "Не начинай с 'Понимаю' — используй другой, естественный переход, "
            "не повторяющий фразы из твоих предыдущих ответов в этом диалоге."
        )

    prompt = (
        "Ты — тёплый, эмпатичный ассистент-консультант по вопросам развода. "
        f"Пользователь только что написал: «{last_text}». "
        f"{style_instruction} "
        f"Затем задай ровно этот вопрос, не меняя его смысл: «{_QUESTIONS[field]}». "
        "Ответ должен звучать как одна живая реплика, без списков."
    )
    result = model.invoke(prompt)
    return {
        "messages": [{"role": "assistant", "content": result.content}],
        "intro_given": True,
    }


def parse_answer(state: DivorceState) -> dict:
    field = get_pending_field(state)
    if field is None:
        return {}

    last_user_message = _get_content(state["messages"][-1])
    auth_key = state["auth_key"]

    classifier = GigaChat(
        credentials=auth_key,
        scope="GIGACHAT_API_PERS",
        model="GigaChat-3-Ultra",
        verify_ssl_certs=False,
        timeout=30,
    )

    prompt = (
        f"Вопрос был: «{_QUESTIONS[field]}»\n"
        f"Ответ пользователя: «{last_user_message}»\n"
        "Определи, что имел в виду пользователь: ДА, НЕТ или НЕПОНЯТНО. "
        "Ответь одним словом, без пояснений."
    )
    result = classifier.invoke(prompt).content.strip().lower()

    if "да" in result:
        return {field: True}
    if "нет" in result:
        return {field: False}
    return {}


def synthesize_answer(state: DivorceState) -> dict:
    auth_key = state["auth_key"]

    facts = (
        f"Известно: общие несовершеннолетние дети — "
        f"{'есть' if state['has_children'] else 'нет'}; "
        f"совместно нажитое имущество для раздела — "
        f"{'есть' if state['has_property'] else 'нет'}; "
        f"оба супруга согласны на развод — "
        f"{'да' if state['both_agree'] else 'нет, есть возражение'}."
    )

    model = GigaChat(
        credentials=auth_key,
        scope="GIGACHAT_API_PERS",
        model="GigaChat-3-Ultra",
        verify_ssl_certs=False,
        timeout=30,
    )

    system_text = (
        "Ты — ассистент-консультант по вопросам расторжения брака в РФ. "
        "Дай общую справочную рекомендацию с учётом собранных фактов. "
        "Обязательно укажи, что это не заменяет консультацию юриста. " + facts
    )

    history_text = "\n".join(
        f"{_get_role(m)}: {_get_content(m)}" for m in state["messages"]
    )

    result = model.invoke(f"{system_text}\n\nИстория диалога:\n{history_text}")
    return {"messages": [{"role": "assistant", "content": result.content}]}


def router(state: DivorceState) -> str:
    if get_pending_field(state) is None:
        return "synthesize"
    return "ask"


graph_builder = StateGraph(DivorceState)
graph_builder.add_node("greet", greet)
graph_builder.add_node("parse", parse_answer)
graph_builder.add_node("ask", ask_next_question)
graph_builder.add_node("synthesize", synthesize_answer)

graph_builder.add_conditional_edges(START, entry_router, {"greet": "greet", "parse": "parse"})
graph_builder.add_edge("greet", END)
graph_builder.add_conditional_edges("parse", router, {"ask": "ask", "synthesize": "synthesize"})
graph_builder.add_edge("ask", END)
graph_builder.add_edge("synthesize", END)
os.makedirs("data", exist_ok=True)
_conn = sqlite3.connect("data/divorce_history.db", check_same_thread=False)
checkpointer = SqliteSaver(_conn)

divorce_graph = graph_builder.compile(checkpointer=checkpointer)