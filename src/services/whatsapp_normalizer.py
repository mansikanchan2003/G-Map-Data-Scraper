import re
from typing import Optional, Tuple

class WhatsAppNormalizer:
    """
    Normalizes and validates phone numbers for WhatsApp Campaigns.
    Canonical format: +91XXXXXXXXXX (13 characters).
    """

    @staticmethod
    def normalize_phone(raw_value: any) -> Tuple[Optional[str], Optional[str]]:
        """
        Normalizes a raw phone number input (from DB, CSV, Excel, etc.)
        Returns a tuple: (canonical_number, error_reason)
        If valid, canonical_number is the +91 string, and error_reason is None.
        If invalid, canonical_number is None, and error_reason is a string explaining why.
        """
        if raw_value is None or str(raw_value).strip() == "":
            return None, "Empty phone number"

        # Handle numeric spreadsheet cells
        if isinstance(raw_value, float):
            # If it's a float like 9911844469.0, it's safe. 
            # If it's 9911844469.5, it's not a valid phone.
            if not raw_value.is_integer():
                return None, "Non-integer phone value"
            raw_value = str(int(raw_value))
        elif isinstance(raw_value, int):
            raw_value = str(raw_value)
        else:
            raw_value = str(raw_value)

        # 1. Trim surrounding whitespace
        cleaned = raw_value.strip()

        # 2. Remove common formatting artifacts (Excel/CSV quotes)
        # We only remove them if they surround the string, or if it's an Excel leading apostrophe.
        # Handle Excel leading apostrophe (e.g. '9911844469)
        if cleaned.startswith("'") and not cleaned.endswith("'") and cleaned.count("'") == 1:
            cleaned = cleaned[1:]

        # Handle surrounding quotes (ASCII and curly)
        quotes = [("\"", "\""), ("'", "'"), ("“", "”"), ("‘", "’")]
        for open_q, close_q in quotes:
            if cleaned.startswith(open_q) and cleaned.endswith(close_q) and len(cleaned) >= 2:
                cleaned = cleaned[1:-1]
        
        # After removing quotes, there might be more whitespace inside the quotes
        cleaned = cleaned.strip()
        
        # At this point, the string should be composed of digits and an optional leading plus.
        # We DO NOT arbitrarily strip spaces in the middle because that might hide invalid formatting 
        # unless we explicitly want to support spaced numbers. The requirements say:
        # "Do NOT blindly accept arbitrary formatting such as 91 99118 44469 unless explicitly validated."
        # "When uncertain: REJECT rather than guess."
        # We'll allow a single plus at the start and digits for the rest.
        if not re.match(r'^\+?[0-9]+$', cleaned):
            return None, "Invalid formatting or characters"

        # Extract digits and check prefix
        has_plus = cleaned.startswith('+')
        digits_only = re.sub(r'[^0-9]', '', cleaned)
        
        # Validate based on lengths and known formats
        # 10 digits -> XXXXXXXXXX
        if len(digits_only) == 10:
            if has_plus:
                return None, "Invalid format (+XXXXXXXXXX not supported)"
            mobile = digits_only
        
        # 12 digits -> 91XXXXXXXXXX
        elif len(digits_only) == 12:
            if digits_only.startswith("91"):
                mobile = digits_only[2:]
            else:
                return None, "Unsupported international number"
                
        else:
            return None, f"Invalid length ({len(digits_only)} digits)"
            
        # Validate the 10-digit mobile number
        # Indian mobile numbers must start with 6, 7, 8, or 9
        # Landlines start with other digits or require STD codes
        if not re.match(r'^[6-9]\d{9}$', mobile):
            if mobile.startswith('0') or mobile.startswith('1') or mobile.startswith('2') or \
               mobile.startswith('3') or mobile.startswith('4') or mobile.startswith('5'):
                return None, "Landline or invalid mobile number"
            return None, "Invalid mobile number"

        canonical = f"+91{mobile}"
        return canonical, None

