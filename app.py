from flask import Flask, render_template, request, jsonify, send_file, abort
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
import os
import re
import requests
from dotenv import load_dotenv

# Загружаем переменные окружения из .env (лежит рядом с app.py)
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

# Инициализация Flask приложения
app = Flask(__name__)

# Читаем API-ключ из переменной окружения (безопасно, не в коде!)
API_KEY = os.getenv('API_KEY')

# Пути к файлам
VOICE_MD_PATH = os.path.join(os.path.dirname(__file__), 'voice.md')
PDF_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), 'theater_post.pdf')

# ------------------------------------------------------------------
# Регистрация шрифта Arial для поддержки кириллицы
# ------------------------------------------------------------------
def register_fonts():
    """
    Регистрирует шрифт Arial для корректного отображения русского текста.
    Пытается найти шрифт в системных папках Windows.
    """
    try:
        # Путь к шрифту Arial в Windows
        arial_path = "C:\\Windows\\Fonts\\arial.ttf"
        arial_bold_path = "C:\\Windows\\Fonts\\arialbd.ttf"
        
        if os.path.exists(arial_path):
            pdfmetrics.registerFont(TTFont('Arial', arial_path))
            print("Шрифт Arial зарегистрирован")
        else:
            print("Шрифт Arial не найден, используются стандартные шрифты")
            
        if os.path.exists(arial_bold_path):
            pdfmetrics.registerFont(TTFont('Arial-Bold', arial_bold_path))
    except Exception as e:
        print(f"Ошибка регистрации шрифта: {e}")

# Регистрируем шрифты при запуске
register_fonts()

# ------------------------------------------------------------------
# Вспомогательные функции для работы с voice.md
# ------------------------------------------------------------------

def read_voice_settings():
    """
    Читает настройки из voice.md.
    Если файл отсутствует, создает его со стандартными значениями.
    Возвращает словарь с настройками.
    """
    default_content = """# Настройки голоса для генерации постов театральных мероприятий

общий_тон: уютный, вдохновляющий, театральный
длина_поста: средняя
количество_эмодзи: 2
стиль_заголовка: восклицательный
дополнительные_указания: использовать театральные метафоры, упоминать атмосферу, кулисы, магию сцены
модель: gpt-5.4-mini
"""
    if not os.path.exists(VOICE_MD_PATH):
        with open(VOICE_MD_PATH, 'w', encoding='utf-8') as f:
            f.write(default_content)
        content = default_content
    else:
        with open(VOICE_MD_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
    
    settings = {}
    # Парсим простые строки вида "ключ: значение"
    # Ищем строки, которые не являются комментариями (#) или пустыми
    for line in content.split('\n'):
        line = line.strip()
        if line and not line.startswith('#') and ':' in line:
            key, value = line.split(':', 1)
            settings[key.strip()] = value.strip()
    
    return settings

# ------------------------------------------------------------------
# Генератор постов (шаблонный, для режима без API)
# ------------------------------------------------------------------

def _generate_template_post(description, genre, mood, settings):
    """
    Шаблонный генератор (резервный, если нет API-ключа).
    Формирует развернутый художественный анонс без вызова LLM.
    """
    tone = settings.get('общий_тон', 'вдохновляющий')
    length = settings.get('длина_поста', 'средняя')
    emoji_count = int(settings.get('количество_эмодзи', '2'))
    title_style = settings.get('стиль_заголовка', 'восклицательный')
    extra = settings.get('дополнительные_указания', '')
    
    emojis = ['🎭', '🎬', '✨', '🔥', '🌟', '🎻', '🎟️']
    
    title_base = f"Анонс: {genre.capitalize()}"
    if title_style == 'восклицательный':
        title = f"{title_base}!"
    else:
        title = title_base
    
    post_emojis = ' '.join(emojis[:emoji_count])
    header = f"{post_emojis} {title} {post_emojis}"
    
    mood_map = {
        'вдохновляющее': 'Почувствуйте дыхание вдохновения! Это событие наполнит ваше сердце светом и теплом, напоминая, что искусство способно исцелять души.',
        'таинственное': 'Мрак и тайны окутывают сцену. Приготовьтесь разгадать загадки, скрытые в тенях кулис.',
        'дерзкое': 'Нарушая правила и ломая стереотипы, этот пост станет вызовом всему привычному!',
        'ностальгическое': 'Окунитесь в атмосферу прошлых лет, где каждое мгновение пропитано воспоминаниями.',
        'эпичное': 'Битвы, страсти и великие свершения ждут вас на самой грандиозной сцене этого сезона!'
    }
    
    mood_text = mood_map.get(mood, 'Незабываемое событие ждет вас.')
    intro = f"Представьте атмосферу, где царит {tone}. Сцена готовится раскрыть свои объятия..."
    main_desc = f"Сюжет разворачивается следующим образом: {description}."
    outro = "Не упустите шанс стать частью этой магии."
    metaphor = f"\n\n{extra}" if extra else ""
    
    if length == 'короткая':
        body = f"{main_desc}\n\n{outro}"
    elif length == 'средняя':
        body = f"{intro}\n\n{main_desc}\n\n{mood_text}\n\n{outro}"
    else:
        body = f"{intro}\n\n{main_desc}\n\n{mood_text}\n\nЗа кулисами кипит жизнь.{metaphor}\n\n{outro}"
    
    post = f"{header}\n\n{body}\n\n#Театр #Искусство #{genre.capitalize()} #Анонс"
    return post


# ------------------------------------------------------------------
# Генератор постов — основная версия (через ProxyAPI/LLM)
# ------------------------------------------------------------------

def generate_post_text(description, genre, mood, settings):
    """
    Генерирует текст поста через ProxyAPI (языковая модель).
    Если API-ключ не указан — использует шаблонный генератор.
    """
    # Если API-ключ не задан, используем шаблон
    if not API_KEY:
        print("API_KEY не найден. Используется шаблонный генератор.")
        return _generate_template_post(description, genre, mood, settings)
    
    # Извлекаем настройки из voice.md
    model = settings.get('модель', 'gpt-5.4-mini')
    tone = settings.get('общий_тон', 'вдохновляющий')
    length = settings.get('длина_поста', 'средняя')
    emoji_count = settings.get('количество_эмодзи', '2')
    title_style = settings.get('стиль_заголовка', 'восклицательный')
    extra = settings.get('дополнительные_указания', '')
    
    # Формируем system-промпт с настройками голоса из voice.md
    system_prompt = f"""Ты — креативный копирайтер театрального блога. Пиши яркие, художественные анонсы.

Настройки стиля (голос поста):
- Общий тон: {tone}
- Длина поста: {length}
- Количество эмодзи: {emoji_count}
- Стиль заголовка: {title_style}
- Дополнительные указания: {extra}

Всегда пиши на русском языке. Используй emoji в заголовке согласно настройкам."""
    
    # Формируем user-промпт с данными от пользователя
    user_prompt = f"""Напиши пост-анонс для театрального мероприятия.

Жанр: {genre}
Настроение поста: {mood}
Описание сюжета/мероприятия: {description}

Требования:
- Пост должен быть оригинальным и эмоциональным
- Соответствовать настроению "{mood}"
- Соблюдать настройки голоса из system-инструкции
- Заканчиваться хэштегами #Театр #Искусство и хэштегом жанра"""
    
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        'temperature': 0.8,
        'max_completion_tokens': 700
    }
    
    try:
        # Отправляем запрос к ProxyAPI (OpenAI-совместимый эндпоинт)
        response = requests.post(
            'https://api.proxyapi.ru/openai/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            post_text = result['choices'][0]['message']['content']
            return post_text.strip()
        else:
            # При ошибке API логируем и используем шаблон
            error_detail = response.text
            print(f"Ошибка API ProxyAPI ({response.status_code}): {error_detail}")
            print("Используется шаблонный генератор (резерв).")
            return _generate_template_post(description, genre, mood, settings)
            
    except requests.exceptions.Timeout:
        print("Таймаут при обращении к ProxyAPI. Используется шаблон.")
        return _generate_template_post(description, genre, mood, settings)
    except Exception as e:
        print(f"Ошибка при вызове LLM: {e}. Используется шаблон.")
        return _generate_template_post(description, genre, mood, settings)

# ------------------------------------------------------------------
# Маршруты Flask
# ------------------------------------------------------------------

@app.route('/')
def index():
    """Главная страница с формой"""
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    """
    Обрабатывает запрос на генерацию поста.
    Принимает JSON: description, genre, mood.
    Возвращает JSON: {post: текст}
    """
    data = request.json
    description = data.get('description', '').strip()
    genre = data.get('genre', 'спектакль')
    mood = data.get('mood', 'вдохновляющее')
    
    # Валидация: описание обязательно
    if not description:
        return jsonify({'error': 'Описание мероприятия обязательно'}), 400
    
    # Читаем настройки голоса
    settings = read_voice_settings()
    
    # Генерируем текст
    post_text = generate_post_text(description, genre, mood, settings)
    
    return jsonify({'post': post_text})

@app.route('/save_pdf', methods=['POST'])
def save_pdf():
    """
    Принимает текст поста и генерирует PDF файл с поддержкой кириллицы и переносов.
    Использует SimpleDocTemplate и Paragraph для корректного рендеринга текста.
    Возвращает файл для скачивания.
    """
    data = request.json
    post_text = data.get('post', '').strip()
    
    if not post_text:
        return jsonify({'error': 'Нет текста для сохранения'}), 400
    
    try:
        # Создаем PDF документ с помощью Platypus (для автоматических переносов)
        # Используем SimpleDocTemplate для управления потоком документа
        doc = SimpleDocTemplate(
            PDF_OUTPUT_PATH,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm,
            # Устанавливаем темный фон (через canvas позже)
        )
        
        # Определяем стили с использованием зарегистрированного шрифта Arial
        # Проверяем, зарегистрирован ли шрифт, иначе используем Helvetica
        try:
            normal_font = 'Arial'
            bold_font = 'Arial-Bold'
        except:
            normal_font = 'Helvetica'
            bold_font = 'Helvetica-Bold'
        
        # Создаем стили для параграфов
        styles = getSampleStyleSheet()
        
        # Стиль для заголовка (тёмный для контраста)
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontName=bold_font,
            fontSize=18,
            textColor=HexColor('#4a148c'),  # Тёмно-фиолетовый
            spaceAfter=14,
            alignment=TA_LEFT
        )
        
        # Стиль для основного текста (чёрный для контраста на белом фоне)
        body_style = ParagraphStyle(
            'BodyStyle',
            parent=styles['Normal'],
            fontName=normal_font,
            fontSize=11,
            textColor=HexColor('#000000'),
            spaceAfter=12,
            leading=16,  # Межстрочный интервал
            alignment=TA_LEFT
        )
        
        # Стиль для даты
        date_style = ParagraphStyle(
            'DateStyle',
            parent=styles['Normal'],
            fontName=normal_font,
            fontSize=8,
            textColor=HexColor('#888888'),
            alignment=TA_LEFT
        )
        
        # Список элементов для добавления в PDF
        story = []
        
        # Добавляем заголовок
        story.append(Paragraph("Театральный Анонс", title_style))
        story.append(Spacer(1, 0.5*cm))
        
        # Обрабатываем текст поста: разбиваем на параграфы по переносам строк
        # Заменяем двойные переносы на новые параграфы
        paragraphs = post_text.split('\n')
        
        for para in paragraphs:
            if para.strip():  # Пропускаем пустые строки
                # Экранируем спецсимволы для XML (ReportLab использует XML-подобный синтаксис)
                para_escaped = para.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                story.append(Paragraph(para_escaped, body_style))
        
        # Добавляем дату внизу
        story.append(Spacer(1, 1*cm))
        from datetime import datetime
        date_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        story.append(Paragraph(f"Сгенерировано: {date_str}", date_style))
        
        # Строим PDF
        doc.build(story)
        
        # Отправляем файл пользователю
        return send_file(
            PDF_OUTPUT_PATH, 
            as_attachment=True, 
            download_name='theater_post.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Ошибка при создании PDF: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Ошибка генерации PDF: {str(e)}'}), 500

# ------------------------------------------------------------------
# Запуск приложения
# ------------------------------------------------------------------

if __name__ == '__main__':
    # Убедимся, что voice.md существует при старте
    read_voice_settings()
    app.run(debug=True, port=5000)
