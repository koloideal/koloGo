from aiogram.fsm.state import State, StatesGroup


class MainMenuSG(StatesGroup):
    main = State()


class RidesSG(StatesGroup):
    list = State()
    detail = State()
    book_confirm = State()


class MyBookingsSG(StatesGroup):
    list = State()
    detail = State()


class BalanceSG(StatesGroup):
    balance = State()


class StatsSG(StatesGroup):
    stats = State()


class AdminPanelSG(StatesGroup):
    main = State()


class RidesMgmtSG(StatesGroup):
    rides_list = State()
    ride_detail = State()


class RideCreateSG(StatesGroup):
    select_template = State()
    calendar = State()
    time = State()
    price = State()
    auto_approve = State()
    visibility = State()
    note = State()
    repeat_days = State()
    confirm = State()


class RideBookingsSG(StatesGroup):
    bookings_list = State()
    booking_detail = State()


class UsersSG(StatesGroup):
    users_list = State()
    user_detail = State()


class DepositSG(StatesGroup):
    deposit_amount = State()
    decrease_amount = State()


class BroadcastSG(StatesGroup):
    text = State()
    confirm = State()


class AdminStatsSG(StatesGroup):
    stats = State()
