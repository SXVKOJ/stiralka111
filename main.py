import asyncio
import os
import datetime
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.types import CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = os.environ.get("TOKEN")

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Пути к CSV-файлам
USER_DB = 'users.csv'
SCHEDULE_DB = 'schedule.csv'

# Загрузка пользователей из CSV
def load_users():
    try:
        df = pd.read_csv(USER_DB)
        users = pd.Series(df.nickname.values, index=df.telegram_id).to_dict()

        return users
    except Exception as e:
        print(e, flush=True)
    
    return {}


users = load_users()

# Инициализация файла расписания
def initialize_schedule():
    df = pd.DataFrame(columns=['date', 'time_slot', 'washing_machine', 'user_id'])
    try:
        df.to_csv(SCHEDULE_DB, index=False)
    except Exception as e:
        print(e, flush=True)

# Сброс расписания каждый понедельник в 00:00
async def reset_schedule():
    while True:
        now = datetime.datetime.now()
        next_monday = now + datetime.timedelta(days=(7 - now.weekday()))
        next_reset = datetime.datetime.combine(next_monday.date(), datetime.time(0, 0))
        wait_time = (next_reset - now).total_seconds()
        await asyncio.sleep(wait_time)
        df = pd.DataFrame(columns=['date', 'time_slot', 'washing_machine', 'user_id'])
        df.to_csv(SCHEDULE_DB, index=False)
        for user_id in users.keys():
            try:
                await bot.send_message(user_id, "Новая неделя! Не забудьте записаться на стирку.")
            except Exception as e:
                print(f"Не удалось отправить сообщение {user_id}: {e}", flush=True)
        await asyncio.sleep(7 * 24 * 60 * 60)

# Обработчик команды /start
@dp.message(Command(commands=['start']))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    if user_id in users:
        await message.answer(
            f"Здравствуйте, {users[user_id]}! Выберите команду:\n"
            "/запись - записаться на стирку\n"
            "/расписание - посмотреть расписание"
        )
    else:
        await message.answer("Извините, у вас нет доступа к стиральной машине.")

# Проверка, записан ли пользователь на текущей неделе
def user_already_registered_this_week(user_id):
    df = load_schedule()
    user_records = df[
        (df['user_id'] == user_id)
    ]
    return not user_records.empty

# Обработчик команды /запись
@dp.message(Command(commands=['запись']))
async def record_command(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("У вас нет доступа к стиральной машине.")
        return

    # Проверка записи на текущую неделю
    if user_already_registered_this_week(user_id):
        await message.answer("Вы уже записаны на этой неделе. Вы не можете записаться повторно.")
        return
    
    now = datetime.datetime.now()
    days = []
    for i in range(7):
        day = now + datetime.timedelta(days=i)
        day_str = day.strftime('%Y-%m-%d')
        if day.date() >= now.date():
            days.append((day_str, day.strftime('%A')))
    
    keyboard = InlineKeyboardBuilder()
    for date_str, day_name in days:
        keyboard.button(text=day_name, callback_data=f"select_day_{date_str}")
    keyboard.adjust(2)
    
    await message.answer("Выберите день:", reply_markup=keyboard.as_markup())

@dp.message(Command(commands=['перезапись']))
async def reschedule_command(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("У вас нет доступа к стиральной машине.")
        return

    # Проверяем, есть ли запись у пользователя
    df = load_schedule()
    user_record = df[df['user_id'] == user_id]
    if user_record.empty:
        await message.answer("У вас нет записи на этой неделе. Вы не можете выполнить перезапись.")
        return

    # Показываем текущую запись
    record = user_record.iloc[0]
    current_date = record['date']
    current_time_slot = record['time_slot']
    current_machine = record['washing_machine']

    await message.answer(
        f"Ваша текущая запись: {current_date} {current_time_slot}, "
        f"{'Машинка ближе к окну' if current_machine == 1 else 'Машинка ближе к двери'}.\n"
        "Выберите новый день для перезаписи."
    )

    # Отправляем список дней
    now = datetime.datetime.now()
    days = []
    for i in range(7):
        day = now + datetime.timedelta(days=i)
        day_str = day.strftime('%Y-%m-%d')
        if day.date() >= now.date():
            days.append((day_str, day.strftime('%A')))
    
    keyboard = InlineKeyboardBuilder()
    for date_str, day_name in days:
        keyboard.button(text=day_name, callback_data=f"reschedule_day_{date_str}")
    keyboard.adjust(2)
    
    await message.answer("Выберите день для перезаписи:", reply_markup=keyboard.as_markup())

# Обработчик выбора нового дня для перезаписи
@dp.callback_query(lambda callback: callback.data.startswith("reschedule_day_"))
async def handle_reschedule_day(callback_query: CallbackQuery):
    selected_date = callback_query.data[len("reschedule_day_"):]
    now = datetime.datetime.now()

    available_times = []
    df = load_schedule()
    for hour in range(14, 23):
        for minute in [0, 30]:
            time_slot = datetime.time(hour, minute)
            if datetime.datetime.strptime(selected_date, "%Y-%m-%d").date() == now.date():
                if datetime.datetime.combine(now.date(), time_slot) <= now:
                    continue
            time_slot_str = time_slot.strftime("%H:%M")
            if df[(df['date'] == selected_date) & (df['time_slot'] == time_slot_str)].shape[0] < 2:
                available_times.append(time_slot_str)

    if not available_times:
        await callback_query.message.edit_text("На выбранный день больше нет доступного времени.")
        await callback_query.answer()
        return

    await callback_query.message.delete()

    keyboard = InlineKeyboardBuilder()
    for time in available_times:
        keyboard.button(text=time, callback_data=f"reschedule_time_{selected_date}_{time}")
    keyboard.adjust(3)

    await callback_query.message.answer(f"Вы выбрали {selected_date}. Теперь выберите время:", reply_markup=keyboard.as_markup())
    await callback_query.message.delete()

# Обработчик выбора нового времени для перезаписи
@dp.callback_query(lambda callback: callback.data.startswith("reschedule_time_"))
async def handle_reschedule_time(callback_query: CallbackQuery):
    data = callback_query.data[len("reschedule_time_"):]
    selected_date, selected_time = data.split("_")
    user_id = callback_query.from_user.id

    # Загружаем записи и проверяем доступные машины
    df = load_schedule()
    machines = {1: "Машинка ближе к окну", 2: "Машинка ближе к двери"}
    available_machines = [m for m in machines if df[(df['date'] == selected_date) & (df['time_slot'] == selected_time) & (df['washing_machine'] == m)].empty]

    if not available_machines:
        await callback_query.message.edit_text("На это время обе стиральные машины уже заняты.")
        await callback_query.answer()
        return

    # Удаляем кнопку времени из сообщения, если все машины заняты
    updated_keyboard = InlineKeyboardBuilder()
    for button in callback_query.message.reply_markup.inline_keyboard:
        for item in button:
            if item.text != selected_time:
                updated_keyboard.button(text=item.text, callback_data=item.callback_data)
    updated_keyboard.adjust(3)
    await callback_query.message.edit_reply_markup(reply_markup=updated_keyboard.as_markup())

    # Отправляем выбор машинки
    keyboard = InlineKeyboardBuilder()
    for machine in available_machines:
        keyboard.button(text=machines[machine], callback_data=f"reschedule_machine_{selected_date}_{selected_time}_{machine}")
    keyboard.adjust(1)

    await callback_query.message.answer("Выберите стиральную машину:", reply_markup=keyboard.as_markup())
    await callback_query.answer()

# Обработчик выбора новой стиральной машины
@dp.callback_query(lambda callback: callback.data.startswith("reschedule_machine_"))
async def handle_reschedule_machine(callback_query: CallbackQuery):
    data = callback_query.data[len("reschedule_machine_"):]
    selected_date, selected_time, machine = data.split("_")
    user_id = callback_query.from_user.id

    # Загружаем расписание и удаляем старую запись
    df = load_schedule()
    df = df[df['user_id'] != user_id]  # Удаляем старую запись пользователя

    # Добавляем новую запись
    new_entry = pd.DataFrame([{
        'date': selected_date,
        'time_slot': selected_time,
        'washing_machine': int(machine),
        'user_id': user_id
    }])
    df = pd.concat([df, new_entry], ignore_index=True)
    df.to_csv(SCHEDULE_DB, index=False)

    await callback_query.message.delete()
    await callback_query.message.answer(
        f"Ваша запись успешно изменена на {selected_date} в {selected_time}.\n"
        f"Стиральная машина: {'Машинка ближе к окну' if machine == '1' else 'Машинка ближе к двери'}."
    )
    await callback_query.answer()


# Обработчик выбора дня
@dp.callback_query(lambda callback: callback.data.startswith("select_day_"))
async def handle_day_selection(callback_query: CallbackQuery):
    selected_date = callback_query.data[len("select_day_"):]
    now = datetime.datetime.now()

    available_times = []
    df = load_schedule()
    for hour in range(14, 23):
        for minute in [0, 30]:
            time_slot = datetime.time(hour, minute)
            if datetime.datetime.strptime(selected_date, "%Y-%m-%d").date() == now.date():
                if datetime.datetime.combine(now.date(), time_slot) <= now:
                    continue
            time_slot_str = time_slot.strftime("%H:%M")
            if df[(df['date'] == selected_date) & (df['time_slot'] == time_slot_str)].shape[0] < 2:
                available_times.append(time_slot_str)

    if not available_times:
        await callback_query.message.edit_text("На выбранный день больше нет доступного времени.")
        await callback_query.answer()
        return

    await callback_query.message.delete()

    keyboard = InlineKeyboardBuilder()
    for time in available_times:
        keyboard.button(text=time, callback_data=f"select_time_{selected_date}_{time}")
    keyboard.adjust(3)

    await callback_query.message.answer(f"Вы выбрали {selected_date}. Теперь выберите время:", reply_markup=keyboard.as_markup())
    await callback_query.answer()
    await callback_query.message.delete()

# Обработчик выбора времени
@dp.callback_query(lambda callback: callback.data.startswith("select_time_"))
async def handle_time_selection(callback_query: CallbackQuery):
    data = callback_query.data[len("select_time_"):]
    selected_date, selected_time = data.split("_")
    user_id = callback_query.from_user.id

    # Загружаем записи и проверяем доступные машины
    df = load_schedule()
    machines = {1: "Машинка ближе к окну", 2: "Машинка ближе к двери"}
    available_machines = [m for m in machines if df[(df['date'] == selected_date) & (df['time_slot'] == selected_time) & (df['washing_machine'] == m)].empty]

    if not available_machines:
        await callback_query.message.edit_text("На это время обе стиральные машины уже заняты.")
        await callback_query.answer()
        return

    # Удаляем кнопку времени из сообщения, если все машины заняты
    updated_keyboard = InlineKeyboardBuilder()
    for button in callback_query.message.reply_markup.inline_keyboard:
        for item in button:
            if item.text != selected_time:
                updated_keyboard.button(text=item.text, callback_data=item.callback_data)
    updated_keyboard.adjust(3)
    await callback_query.message.edit_reply_markup(reply_markup=updated_keyboard.as_markup())

    # Отправляем выбор машинки
    keyboard = InlineKeyboardBuilder()
    for machine in available_machines:
        keyboard.button(text=machines[machine], callback_data=f"select_machine_{selected_date}_{selected_time}_{machine}")
    keyboard.adjust(1)

    await callback_query.message.answer("Выберите стиральную машину:", reply_markup=keyboard.as_markup())
    await callback_query.answer()
    await callback_query.message.delete()

# Обработчик выбора машинки
@dp.callback_query(lambda callback: callback.data.startswith("select_machine_"))
async def handle_machine_selection(callback_query: CallbackQuery):
    data = callback_query.data[len("select_machine_"):]
    selected_date, selected_time, machine = data.split("_")
    user_id = callback_query.from_user.id

    # Сохраняем запись
    df = load_schedule()
    new_entry = pd.DataFrame([{
        'date': selected_date,
        'time_slot': selected_time,
        'washing_machine': int(machine),
        'user_id': user_id
    }])
    df = pd.concat([df, new_entry], ignore_index=True)
    df.to_csv(SCHEDULE_DB, index=False)

    await callback_query.message.delete()
    await callback_query.message.answer(
        f"Вы успешно записались на {selected_date} в {selected_time}.\n"
        f"Стиральная машина: {'Машинка ближе к окну' if machine == '1' else 'Машинка ближе к двери'}."
    )
    await callback_query.answer()
    await callback_query.message.delete()

# Напоминание перед стиркой
async def send_reminders():
    while True:
        now = datetime.datetime.now()
        df = load_schedule()

        # Проверяем стирки на ближайшие 30 минут
        upcoming = df[df['date'] == now.strftime('%Y-%m-%d')]  # Сегодняшние записи
        for _, record in upcoming.iterrows():
            time_slot = datetime.datetime.strptime(f"{record['date']} {record['time_slot']}", "%Y-%m-%d %H:%M")
            time_difference = (time_slot - now).total_seconds()

            # Если до стирки осталось от 5 до 30 минут
            if 0 < time_difference <= 1800:
                user_id = record['user_id']
                machine = "Машинка ближе к окну" if record['washing_machine'] == 1 else "Машинка ближе к двери"
                try:
                    await bot.send_message(
                        user_id,
                        f"Напоминание: у вас стирка через {int(time_difference // 60)} минут.\n"
                        f"Дата: {record['date']}, время: {record['time_slot']}, {machine}."
                    )
                except Exception as e:
                    print(f"Не удалось отправить напоминание пользователю {user_id}: {e}", flush=True)

        await asyncio.sleep(60*10)  # Проверяем каждые 60 секунд

# Загрузка расписания
def load_schedule():
    try:
        r = pd.read_csv(SCHEDULE_DB)

        return r
    except Exception as e:
        print(e, flush=True)

    return {}

# Обработчик команды /расписание
@dp.message(Command(commands=['расписание']))
async def schedule_command(message: types.Message):
    df = load_schedule()
    if df.empty:
        await message.answer("Расписание пусто.")
        return

    schedule_text = "Расписание стирок:\n"
    grouped = df.groupby('date')

    for date, group in grouped:
        schedule_text += f"\nДата: {date}\n"
        for _, row in group.iterrows():
            time_slot = row['time_slot']
            machine = row['washing_machine']
            user_id = row['user_id']
            nickname = users.get(user_id, "Неизвестный пользователь")
            schedule_text += f"- {time_slot}, {'Машинка ближе к окну' if machine == 1 else 'Машинка ближе к двери'}: {nickname}\n"

    await message.answer(schedule_text)

# Точка входа
async def main():
    initialize_schedule()
    asyncio.create_task(reset_schedule())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
