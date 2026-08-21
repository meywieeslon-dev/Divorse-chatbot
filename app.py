import os
import time
import uuid
from graph import divorce_graph, _get_content, _get_role


import httpx
import requests
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from guardrails import check_input, check_output, SYSTEM_PROMPT, REFUSAL_MESSAGE


load_dotenv()

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
BASE_URL = "https://api.giga.chat/v1"
MODEL = "GigaChat-3-Ultra"


def get_access_token(auth_key: str) -> str:
    auth_key = auth_key.strip()
    now = time.time()
    cached = st.session_state.get("_token_cache")
    if cached and cached["expires_at"] - now > 60:
        return cached["token"]

    resp = requests.post(
        OAUTH_URL,
        data="scope=GIGACHAT_API_PERS",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Bearer {auth_key}",
        },
        verify=False,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    st.session_state["_token_cache"] = {
        "token": data["access_token"],
        "expires_at": data["expires_at"] / 1000,
    }
    return data["access_token"]


def get_client(auth_key: str) -> OpenAI:
    token = get_access_token(auth_key)
    http_client = httpx.Client(verify=False)
    return OpenAI(api_key=token, base_url=BASE_URL, http_client=http_client)



st.set_page_config(page_title="Помощник при разводе", page_icon="assets/mascot.jpg")

st.markdown(
    """
    <style>
    .block-container {
        max-width: 700px;
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    [data-testid="stChatMessage"] {
        border-radius: 16px;
        padding: 6px 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

left, center, right = st.columns([1, 2, 1])
with center:
    st.image("assets/mascot.jpg", use_container_width=True)

st.markdown("<h1 style='text-align: center;'>Чат-консультант по разводам</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align: center; color: #8a8a8a;'>"
    "Отвечает на общие вопросы о процедуре развода в РФ"
    "</p>",
    unsafe_allow_html=True,
)
st.divider()


auth_key = os.environ.get("GIGACHAT_AUTH_KEY", "")
if not auth_key:
    auth_key = st.sidebar.text_input("GigaChat Authorization Key", type="password")

if "divorce_state" not in st.session_state:
    st.session_state.divorce_state = {
        "messages": [],
        "has_children": None,
        "has_property": None,
        "both_agree": None,
        "auth_key": auth_key,
        "greeted": False,
        "intro_given": False,
    }

for msg in st.session_state.divorce_state["messages"]:
    with st.chat_message(_get_role(msg)):
        st.markdown(_get_content(msg))

user_input = st.chat_input("Ваш вопрос про развод...")

if user_input and not auth_key:
    st.error("Не найден ключ GigaChat. Проверьте файл .env")
elif user_input:
    st.session_state.divorce_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        verdict = check_input(user_input)
        if not verdict.allowed:
            answer = REFUSAL_MESSAGE.format(reason=verdict.reason)
            st.markdown(answer)
            st.session_state.divorce_state["messages"].append(
                {"role": "assistant", "content": answer}
            )
        else:
            try:
                st.session_state.divorce_state["auth_key"] = auth_key  # на случай, если ключ изменился
                result_state = divorce_graph.invoke(st.session_state.divorce_state)
                st.session_state.divorce_state = result_state
                answer = _get_content(result_state["messages"][-1])

                out_verdict = check_output(answer)
                if not out_verdict.allowed:
                    answer = REFUSAL_MESSAGE.format(reason=out_verdict.reason)

                st.markdown(answer)
            except Exception as e:  # noqa: BLE001
                answer = f"Непредвиденная ошибка: {e}"
                st.error(answer)