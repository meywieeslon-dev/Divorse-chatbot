import os
import uuid

import streamlit as st

from graph import divorce_graph, _get_content, _get_role
from guardrails import check_input, check_output, REFUSAL_MESSAGE
from dotenv import load_dotenv

load_dotenv()

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
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
        flex-direction: row-reverse;
        text-align: right;
        margin-left: 15%;
        background-color: #E8EEF3;
    }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
        margin-right: 15%;
        background-color: #F0F4F8;
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

if "thread_id" not in st.query_params:
    new_thread_id = str(uuid.uuid4())
    st.query_params["thread_id"] = new_thread_id

thread_id = st.query_params["thread_id"]

if "divorce_state" not in st.session_state:
    existing = divorce_graph.get_state({"configurable": {"thread_id": thread_id}})
    if existing and existing.values:
        st.session_state.divorce_state = existing.values
    else:
        st.session_state.divorce_state = {"messages": []}

for msg in st.session_state.divorce_state.get("messages", []):
    with st.chat_message(_get_role(msg)):
        st.markdown(_get_content(msg))

user_input = st.chat_input("Ваш вопрос про развод...")

if user_input and not auth_key:
    st.error("Не найден ключ GigaChat. Проверьте секреты приложения.")
elif user_input:
    st.session_state.divorce_state.setdefault("messages", []).append(
        {"role": "user", "content": user_input}
    )
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("_печатает..._")

        verdict = check_input(user_input)
        if not verdict.allowed:
            answer = REFUSAL_MESSAGE.format(reason=verdict.reason)
            placeholder.markdown(answer)
            st.session_state.divorce_state["messages"].append(
                {"role": "assistant", "content": answer}
            )
        else:
            try:
                result_state = divorce_graph.invoke(
                    {
                        "messages": [{"role": "user", "content": user_input}],
                        "auth_key": auth_key,
                    },
                    config={"configurable": {"thread_id": thread_id}},
                )
                answer = _get_content(result_state["messages"][-1])

                out_verdict = check_output(answer)
                if not out_verdict.allowed:
                    answer = REFUSAL_MESSAGE.format(reason=out_verdict.reason)

                placeholder.markdown(answer)

                final_state = divorce_graph.get_state(
                    {"configurable": {"thread_id": thread_id}}
                )
                st.session_state.divorce_state = final_state.values

            except Exception as e:
                answer = f"Непредвиденная ошибка: {e}"
                st.error(answer)