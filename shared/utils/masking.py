import re

def mask_cpf_cnpj(value):
    if not value:
        return value
    # Remove non-digits
    digits = re.sub(r'\D', '', value)
    
    if len(digits) == 11:
        # CPF format: XXX.XXX.XXX-XX -> ***.***.123-45
        return f"***.***.{digits[6:9]}-{digits[9:11]}"
    elif len(digits) == 14:
        # CNPJ format: XX.XXX.XXX/XXXX-XX -> **.***.***.0001-XX
        return f"**.***.***/{digits[8:12]}-{digits[12:14]}"
    
    # If not 11 or 14 digits, just mask the first half
    half = len(value) // 2
    return '*' * half + value[half:]

def mask_email(value):
    if not value or '@' not in value:
        return value
    local_part, domain = value.split('@', 1)
    if len(local_part) <= 2:
        masked_local = '*' * len(local_part)
    else:
        masked_local = f"{local_part[0]}{'*' * (len(local_part) - 2)}{local_part[-1]}"
    return f"{masked_local}@{domain}"

def mask_phone(value):
    if not value:
        return value
    digits = re.sub(r'\D', '', value)
    if len(digits) >= 8:
        # Mask everything except last 4 digits
        visible = value[-4:]
        hidden = re.sub(r'\d', '*', value[:-4])
        return hidden + visible
    return '*' * len(value)
