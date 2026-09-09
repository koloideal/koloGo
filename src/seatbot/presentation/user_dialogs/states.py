from aiogram.fsm.state import State, StatesGroup


class MainMenuSG(StatesGroup):
    main = State()


class VipSG(StatesGroup):
    info = State()


class BalanceSG(StatesGroup):
    balance = State()
    top_up_amount = State()
    top_up_method = State()
    invoice = State()


class RidesSG(StatesGroup):
    list = State()
    detail = State()
    book_confirm = State()


class MyBookingsSG(StatesGroup):
    list = State()
    detail = State()


class StatsSG(StatesGroup):
    stats = State()


class RequisitesSG(StatesGroup):
    list = State()


class AdminPanelSG(StatesGroup):
    main = State()


class RidesMgmtSG(StatesGroup):
    rides_list = State()
    ride_detail = State()
    complete_confirm = State()
    change_time = State()


class RideCreateSG(StatesGroup):
    select_template = State()
    calendar = State()
    time = State()
    price = State()
    auto_approve = State()
    visibility = State()
    note = State()
    repeat_days = State()
    remind = State()
    vip_hold = State()
    confirm = State()


class RideBookingsSG(StatesGroup):
    bookings_list = State()
    booking_detail = State()
    add_passenger = State()
    kick_reason = State()
    broadcast_text = State()
    broadcast_confirm = State()


class UsersSG(StatesGroup):
    users_list = State()
    user_detail = State()
    search = State()
    search_results = State()


class DepositSG(StatesGroup):
    deposit_amount = State()
    decrease_amount = State()


class BroadcastSG(StatesGroup):
    text = State()
    confirm = State()


class AdminStatsSG(StatesGroup):
    stats = State()


class AdminRequisitesSG(StatesGroup):
    list = State()
    title = State()
    value = State()
    detail = State()


class AdminSettingsSG(StatesGroup):
    main = State()
    vip_price = State()
    byn_rate = State()
    stars_rate = State()
