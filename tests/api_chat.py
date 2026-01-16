#!/usr/bin/env python3
"""Test Kotaemon chat via Gradio API.

Usage:
  python tests/api_chat.py "What is Credo?"
  python tests/api_chat.py "Is Cadent cost of heat failures in scope?"
"""

import sys
from gradio_client import Client


def chat(question: str, index: str = 'credo4') -> str:
    """
    Send a question to Kotaemon via Gradio API.

    Args:
        question: The question to ask
        index: Which index to use ('file', 'graphrag', 'lightrag', 'credo4')
    """
    client = Client('http://localhost:3000')

    # Login
    client.predict(usn='admin', pwd='admin', api_name="/login")

    # Submit message
    result = client.predict(
        chat_input={'text': question, 'files': []},
        chat_history=[],
        conv_name=None,
        first_selector_choices=[],
        api_name="/submit_msg"
    )
    chat_history = result[1]

    # Map index name to params
    # param_11/12 = File Collection (index 1)
    # param_14/15 = GraphRAG Collection (index 2)
    # param_17/18 = LightRAG Collection (index 3)
    # param_20/21 = Credo4 (index 4)
    index_params = {
        'file':     {'param_11': 'all', 'param_14': 'disabled', 'param_17': 'disabled', 'param_20': 'disabled'},
        'graphrag': {'param_11': 'disabled', 'param_14': 'all', 'param_17': 'disabled', 'param_20': 'disabled'},
        'lightrag': {'param_11': 'disabled', 'param_14': 'disabled', 'param_17': 'all', 'param_20': 'disabled'},
        'credo4':   {'param_11': 'disabled', 'param_14': 'disabled', 'param_17': 'disabled', 'param_20': 'all'},
    }
    params = index_params.get(index, index_params['credo4'])

    # Call chat function
    chat_result = client.predict(
        chat_history=chat_history,
        llm_type='ollama',
        use_citation='highlight',
        language='en',
        param_11=params['param_11'],
        param_12=[],
        param_14=params['param_14'],
        param_15=[],
        param_17=params['param_17'],
        param_18=[],
        param_20=params['param_20'],
        param_21=[],
        api_name="/chat_fn"
    )

    # Extract answer
    if chat_result and chat_result[0]:
        last_msg = chat_result[0][-1]
        if isinstance(last_msg, (list, tuple)) and len(last_msg) >= 2:
            return last_msg[1]
    return "No response"


if __name__ == '__main__':
    question = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else 'What is Credo?'
    print(f"Q: {question}")
    print(f"\nA: {chat(question)}")
