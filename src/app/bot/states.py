from aiogram.fsm.state import State, StatesGroup


class TicketCreateState(StatesGroup):
    waiting_subject = State()
    waiting_message = State()


class TicketReplyState(StatesGroup):
    waiting_ticket_id = State()
    waiting_message = State()

