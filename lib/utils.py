import datetime

def format_currency(amount, currency='soles') -> str:
    """Formats numeric amounts as currency strings."""
    if amount is None:
        amount = 0.0
    symbol = "S/" if currency.lower() == 'soles' else "$"
    return f"{symbol} {amount:,.2f}"

def get_day_name_spanish(date_obj) -> str:
    """Returns the name of the day in Spanish, matching our payroll days schema."""
    days = {
        0: "lunes",
        1: "martes",
        2: "miercoles",
        3: "jueves",
        4: "viernes",
        5: "sabado",
        6: "domingo"
    }
    # date.weekday() returns 0 for Monday, 6 for Sunday
    return days[date_obj.weekday()]

def number_to_spanish_words(number) -> str:
    """
    Converts a number (float or int) to its written equivalent in Spanish (e.g. 1045.00 -> 'Un mil cuarenta y cinco con 00/100 Soles').
    """
    if number is None:
        return "Cero con 00/100 Soles"
        
    # Split integer and decimal parts
    integer_part = int(abs(number))
    decimal_part = int(round((abs(number) - integer_part) * 100))
    
    # Text lookup dictionaries
    UNIDADES = ["", "un", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"]
    DECENAS = ["", "diez", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
    ESPECIALES = {
        10: "diez", 11: "once", 12: "doce", 13: "trece", 14: "catorce", 15: "quince",
        16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve",
        21: "veintiuno", 22: "veintidós", 23: "veintitrés", 24: "veinticuatro",
        25: "veinticinco", 26: "veintiséis", 27: "veintissiete", 28: "veintiocho", 29: "veintinueve"
    }
    CENTENAS = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos", "ochocientos", "novecientos"]

    def _convert_group(n):
        """Converts a number under 1000 to Spanish words."""
        if n == 0:
            return ""
        if n == 100:
            return "cien"
            
        c = n // 100
        d = (n % 100) // 10
        u = n % 10
        
        words = []
        if c > 0:
            words.append(CENTENAS[c])
            
        rem = n % 100
        if rem > 0:
            if rem in ESPECIALES:
                words.append(ESPECIALES[rem])
            else:
                if d > 0:
                    dec_word = DECENAS[d]
                    if u > 0:
                        words.append(f"{dec_word} y {UNIDADES[u]}")
                    else:
                        words.append(dec_word)
                else:
                    words.append(UNIDADES[u])
                    
        return " ".join(words)

    if integer_part == 0:
        texto = "cero"
    else:
        # We handle up to millions
        millones = integer_part // 1000000
        miles = (integer_part % 1000000) // 1000
        unidades = integer_part % 1000
        
        parts = []
        
        if millones > 0:
            if millones == 1:
                parts.append("un millón")
            else:
                parts.append(f"{_convert_group(millones)} millones")
                
        if miles > 0:
            if miles == 1:
                parts.append("un mil") # In Peru, 'un mil' or 'mil' are both used, 'un mil' matches the reference document
            else:
                parts.append(f"{_convert_group(miles)} mil")
                
        if unidades > 0:
            parts.append(_convert_group(unidades))
            
        texto = " ".join(parts).strip()

    # Capitalize the first letter
    texto = texto[0].upper() + texto[1:] if texto else ""
    
    # Format the final string
    words_repr = f"{texto} con {decimal_part:02d}/100 Soles"
    return words_repr
