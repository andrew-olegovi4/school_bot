import re
from typing import Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from school_bot.config import SCHOOL_URL


async def parse_school_info() -> Dict[str, Optional[str]]:
    """Точный парсинг информации о школе для вашего сайта"""
    default_info = {
        'name': None,
        'address': None,
        'director': None,
        'phones': None,
        'email': None,
        'description': None
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(SCHOOL_URL)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            info = default_info.copy()

            # 1. Парсим название школы (берем третий h2 с указанным классом)
            name_tags = soup.find_all('h2', class_='name tpl-text-header2')
            if len(name_tags) >= 3:  # Проверяем, что есть хотя бы 3 элемента
                name_tag = name_tags[2]  # Берем третий элемент (индексация с 0)
                name = name_tag.get_text(strip=True).replace('&quot;', '"')
                info['name'] = name.split(':')[0].strip()
            
            # 2. Парсим адрес из object-index-text
            object_index = soup.find('div', class_='object-index-text')
            if object_index:
                address_tag = object_index.find('div', class_='address')
                if address_tag:
                    info['address'] = address_tag.get_text(strip=True)

            # 3. Парсим описание
            description_tag = soup.find('article', class_='tpl-text-default')
            if description_tag:
                description = description_tag.find('p').get_text(strip=True)
                info['description'] = description.replace('&quot;', '"').replace('  ', ' ')

            # 4. Парсим контакты (остальной код без изменений)
            contact_block = soup.find('div', class_='tpl-component-gw-staff')
            if contact_block:
                # Директор
                director_tag = contact_block.find('a', attrs={'title': True})
                if director_tag:
                    director_name = director_tag['title'].strip()
                    director_position = contact_block.find('div', class_='contacts-object-info-subname')
                    position = director_position.get_text(strip=True) if director_position else "Директор"
                    info['director'] = f"{position}: {director_name}"

                # Телефоны
                phone_header = contact_block.find('div', class_='tpl-text-header6', string=lambda t: 'Телефон' in str(t))
                if phone_header:
                    phone_div = phone_header.find_next('div', class_='tpl-text-default-paragraph')
                    if phone_div:
                        info['phones'] = phone_div.get_text(strip=True).replace(' - ', '-')

                # Email
                email_header = contact_block.find('div', class_='tpl-text-header6', string=lambda t: 'Электронная почта' in str(t))
                if email_header:
                    email_div = email_header.find_next('div', class_='tpl-text-default-paragraph')
                    if email_div:
                        info['email'] = email_div.get_text(strip=True)

            # Формируем контакты
            contacts = []
            if info['phones']:
                contacts.append(f"📞 Телефоны: {info['phones']}")
            if info['email']:
                contacts.append(f"📧 Email: {info['email']}")
            if info['address']:
                contacts.append(f"📍 Адрес: {info['address']}")
            
            info['contacts'] = "\n".join(contacts) if contacts else None

            return info

    except Exception as e:
        print(f"Ошибка парсинга: {e}")
        return default_info


async def parse_school_schedule() -> List[Dict[str, str]]:
    """Парсит все PDF с расписанием с сайта школы"""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:  # Увеличиваем таймаут для загрузки файлов
            # Получаем страницу с расписанием
            response = await client.get(f"{SCHOOL_URL}glavnoe/raspisanie/")
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            schedules = []
            
            # Находим все блоки с документами
            doc_items = soup.find_all('div', class_='document-object-item')
            
            for item in doc_items:
                # Извлекаем название расписания
                name_tag = item.find('div', class_='document-caption')
                name = name_tag.get_text(strip=True).replace('&quot;', '"') if name_tag else "Расписание"
                
                # Извлекаем ссылку на PDF
                download_link = item.find('a', class_='document-download')
                if download_link and download_link.get('href'):
                    pdf_url = download_link['href']
                    # Если ссылка относительная, делаем абсолютной
                    if not pdf_url.startswith('http'):
                        pdf_url = f"{SCHOOL_URL.rstrip('/')}{pdf_url}"
                    
                    schedules.append({
                        'name': name,
                        'url': pdf_url
                    })
            
            return schedules

    except Exception as e:
        print(f"Ошибка парсинга расписания: {e}")
        return []