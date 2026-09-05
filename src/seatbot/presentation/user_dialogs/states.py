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


class AdminSG(StatesGroup):
    main = State()
    rides_list = State()
    ride_detail = State()
    ride_create_departure = State()
    ride_create_price = State()
    ride_create_seats = State()
    ride_create_auto_approve = State()
    ride_create_visibility = State()
    ride_create_note = State()
    ride_create_confirm = State()
    ride_bookings_list = State()
    booking_detail = State()
    users_list = State()
    user_detail = State()
    user_deposit_amount = State()
    user_decrease_amount = State()
    broadcast_text = State()
    broadcast_confirm = State()
    stats = State()
