from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from barq_support.agent import agent as agent_module


def _run_agent(monkeypatch, public_key="", secret_key=""):
    settings = SimpleNamespace(
        agent_max_iterations=5,
        langfuse_public_key=public_key,
        langfuse_secret_key=secret_key,
        langfuse_host="https://cloud.langfuse.com",
    )
    fake_agent = Mock()
    fake_agent.invoke.return_value = {"s3_terminal_called": True}
    fake_client = Mock()

    monkeypatch.setattr(
        "barq_support.agent.tools.build_tools",
        lambda **kwargs: ([], []),
    )
    monkeypatch.setattr(agent_module, "build_llm", lambda settings: object())
    monkeypatch.setattr(agent_module, "build_agent", lambda **kwargs: fake_agent)
    monkeypatch.setattr(agent_module, "Langfuse", Mock())
    monkeypatch.setattr(agent_module, "get_client", Mock(return_value=fake_client))
    monkeypatch.setattr(agent_module, "CallbackHandler", Mock())

    result = agent_module.run_agent(
        settings=settings,
        incident={
            "sys_id": "incident-id",
            "number": "INC001",
            "short_description": "Test",
            "description": "Test",
            "category": "software",
        },
        servicenow=object(),
        qdrant_client=object(),
    )
    return result, fake_agent, fake_client


def test_run_agent_skips_langfuse_when_credentials_are_unset(monkeypatch):
    result, fake_agent, fake_client = _run_agent(monkeypatch)

    assert result == {"s3_terminal_called": True}
    assert fake_agent.invoke.call_args.kwargs["config"] == {}
    agent_module.Langfuse.assert_not_called()
    agent_module.get_client.assert_not_called()
    agent_module.CallbackHandler.assert_not_called()
    fake_client.flush.assert_not_called()


def test_run_agent_enables_langfuse_when_credentials_are_set(monkeypatch):
    result, fake_agent, fake_client = _run_agent(
        monkeypatch,
        public_key="public",
        secret_key="secret",
    )

    assert result == {"s3_terminal_called": True}
    agent_module.Langfuse.assert_called_once_with(
        public_key="public",
        secret_key="secret",
        host="https://cloud.langfuse.com",
    )
    agent_module.get_client.assert_called_once_with(public_key="public")
    callback = agent_module.CallbackHandler.return_value
    agent_module.CallbackHandler.assert_called_once_with(public_key="public")
    assert fake_agent.invoke.call_args.kwargs["config"] == {
        "callbacks": [callback],
    }
    fake_client.flush.assert_called_once_with()


def test_run_agent_rejects_partial_langfuse_credentials(monkeypatch):
    settings = SimpleNamespace(
        agent_max_iterations=5,
        langfuse_public_key="public",
        langfuse_secret_key="",
        langfuse_host="https://cloud.langfuse.com",
    )
    monkeypatch.setattr(
        "barq_support.agent.tools.build_tools",
        lambda **kwargs: ([], []),
    )
    monkeypatch.setattr(agent_module, "build_llm", lambda settings: object())
    monkeypatch.setattr(agent_module, "build_agent", lambda **kwargs: object())

    with pytest.raises(ValueError, match="Both LANGFUSE_PUBLIC_KEY"):
        agent_module.run_agent(
            settings=settings,
            incident={
                "sys_id": "incident-id",
                "number": "INC001",
                "short_description": "Test",
                "description": "Test",
                "category": "software",
            },
            servicenow=object(),
            qdrant_client=object(),
        )
