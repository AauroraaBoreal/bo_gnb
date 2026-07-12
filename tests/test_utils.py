import datetime
import pytest
from lib.utils import format_currency, get_day_name_spanish, number_to_spanish_words

def test_format_currency():
    assert format_currency(10.50, 'soles') == "S/ 10.50"
    assert format_currency(2500, 'soles') == "S/ 2,500.00"
    assert format_currency(123.456, 'dollars') == "$ 123.46"
    assert format_currency(None) == "S/ 0.00"

def test_get_day_name_spanish():
    # 2026-07-11 was a Saturday (sabado)
    assert get_day_name_spanish(datetime.date(2026, 7, 11)) == "sabado"
    # 2026-07-12 was a Sunday (domingo)
    assert get_day_name_spanish(datetime.date(2026, 7, 12)) == "domingo"
    # 2026-07-13 was a Monday (lunes)
    assert get_day_name_spanish(datetime.date(2026, 7, 13)) == "lunes"

def test_number_to_spanish_words():
    # Test cases for numbers in Spanish words
    assert number_to_spanish_words(None) == "Cero con 00/100 Soles"
    assert number_to_spanish_words(0) == "Cero con 00/100 Soles"
    assert number_to_spanish_words(1045.00) == "Un mil cuarenta y cinco con 00/100 Soles"
    assert number_to_spanish_words(25.50) == "Veinticinco con 50/100 Soles"
    assert number_to_spanish_words(100.00) == "Cien con 00/100 Soles"
    assert number_to_spanish_words(1000000.00) == "Un millón con 00/100 Soles"
    assert number_to_spanish_words(2345678.90) == "Dos millones trescientos cuarenta y cinco mil seiscientos setenta y ocho con 90/100 Soles"
