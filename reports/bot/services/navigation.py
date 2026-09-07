"""Navigation stack and conversation state."""

from __future__ import annotations

from typing import Any

from reports.models import BotConversationState


class BotNavigationService:
    @staticmethod
    def get_state(bale_user_id: int) -> BotConversationState:
        state, _ = BotConversationState.objects.get_or_create(bale_user_id=bale_user_id)
        return state

    @classmethod
    def set_flow(cls, bale_user_id: int, flow: str, **context: Any) -> BotConversationState:
        state = cls.get_state(bale_user_id)
        state.flow_state = flow
        if context:
            ctx = dict(state.context or {})
            ctx.update(context)
            state.context = ctx
        state.save(update_fields=["flow_state", "context", "updated_at"])
        return state

    @classmethod
    def clear_flow(cls, bale_user_id: int) -> None:
        state = cls.get_state(bale_user_id)
        state.flow_state = ""
        state.context = {}
        state.save(update_fields=["flow_state", "context", "updated_at"])

    @classmethod
    def push_screen(cls, bale_user_id: int, screen: str) -> list[str]:
        state = cls.get_state(bale_user_id)
        stack = list(state.nav_stack or [])
        if not stack or stack[-1] != screen:
            stack.append(screen)
        state.nav_stack = stack
        state.save(update_fields=["nav_stack", "updated_at"])
        return stack

    @classmethod
    def replace_screen(cls, bale_user_id: int, screen: str) -> list[str]:
        state = cls.get_state(bale_user_id)
        stack = list(state.nav_stack or [])
        if stack:
            stack[-1] = screen
        else:
            stack = [screen]
        state.nav_stack = stack
        state.save(update_fields=["nav_stack", "updated_at"])
        return stack

    @classmethod
    def pop_screen(cls, bale_user_id: int) -> str:
        state = cls.get_state(bale_user_id)
        stack = list(state.nav_stack or [])
        if len(stack) > 1:
            stack.pop()
        elif stack:
            stack = ["main"]
        else:
            stack = ["main"]
        state.nav_stack = stack
        state.save(update_fields=["nav_stack", "updated_at"])
        return stack[-1] if stack else "main"

    @classmethod
    def reset_to_main(cls, bale_user_id: int) -> str:
        state = cls.get_state(bale_user_id)
        state.nav_stack = ["main"]
        state.flow_state = ""
        state.context = {}
        state.save(update_fields=["nav_stack", "flow_state", "context", "updated_at"])
        return "main"

    @classmethod
    def current_screen(cls, bale_user_id: int) -> str:
        state = cls.get_state(bale_user_id)
        stack = state.nav_stack or []
        return stack[-1] if stack else "main"

    @classmethod
    def set_menu_message(cls, bale_user_id: int, chat_id: int, message_id: int) -> None:
        state = cls.get_state(bale_user_id)
        state.menu_chat_id = chat_id
        state.menu_message_id = message_id
        state.save(update_fields=["menu_chat_id", "menu_message_id", "updated_at"])

    @classmethod
    def get_context(cls, bale_user_id: int) -> dict:
        return dict(cls.get_state(bale_user_id).context or {})

    @classmethod
    def update_context(cls, bale_user_id: int, **kwargs: Any) -> dict:
        state = cls.get_state(bale_user_id)
        ctx = dict(state.context or {})
        ctx.update(kwargs)
        state.context = ctx
        state.save(update_fields=["context", "updated_at"])
        return ctx
