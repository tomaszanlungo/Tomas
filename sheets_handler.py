import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from config import SPREADSHEET_ID

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Mapeo de campo → número de columna (1-indexed)
_COLUMNS = {
    "fecha": 1,
    "descripcion": 2,
    "monto": 3,
    "categoria": 4,
    "metodo_pago": 5,
}

_CATEGORIES = [
    "Comida", "Transporte", "Entretenimiento", "Salud",
    "Hogar", "Ropa", "Educación", "Tecnología", "Otros",
]

MONTH_NAMES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def _get_spreadsheet():
    creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)


def _get_worksheet():
    return _get_spreadsheet().worksheet("Control de Gastos")


# --- Gastos ---

def append_expense(date, description, amount, category, payment_method) -> int:
    """
    Agrega una nueva fila al final de la hoja.
    Retorna el número de fila (1-indexed) donde se guardó.
    """
    worksheet = _get_worksheet()
    worksheet.append_row(
        [date, description, amount, category, payment_method],
        value_input_option="USER_ENTERED",
    )
    return len(worksheet.get_all_values())


def get_last_row_number() -> int:
    """Fallback: devuelve el número de la última fila con datos."""
    return len(_get_worksheet().get_all_values())


def update_last_expense(fields: dict, row_number: int = None) -> int:
    """
    Actualiza parcialmente la fila indicada (o la última si row_number es None).
    Retorna el número de fila actualizado.
    """
    worksheet = _get_worksheet()
    if row_number is None:
        row_number = len(worksheet.get_all_values())

    for field, value in fields.items():
        col = _COLUMNS.get(field)
        if col:
            worksheet.update_cell(row_number, col, value)

    return row_number


# --- Reportes ---

def get_monthly_summary(month: int, year: int) -> dict:
    """
    Lee todos los gastos y devuelve un resumen del mes/año indicado.

    Retorna:
    {
        "month": 3, "year": 2026, "month_name": "Marzo",
        "by_category": {"Comida": 15000.0, "Transporte": 5000.0, ...},
        "total": 20000.0,
        "count": 12
    }
    """
    worksheet = _get_worksheet()
    rows = worksheet.get_all_values()

    _DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]
    by_category: dict[str, float] = {}
    count = 0

    for row in rows:
        if len(row) < 5:
            continue
        fecha_raw, _, monto_raw, categoria, _ = row[0], row[1], row[2], row[3], row[4]

        # Parsea la fecha con cualquier formato conocido
        parsed_date = None
        for fmt in _DATE_FORMATS:
            try:
                parsed_date = datetime.strptime(fecha_raw.strip(), fmt)
                break
            except ValueError:
                continue
        if parsed_date is None or parsed_date.month != month or parsed_date.year != year:
            continue

        try:
            monto = float(str(monto_raw).replace(",", ".").replace("$", "").replace(" ", "").strip())
        except ValueError:
            continue
        by_category[categoria] = by_category.get(categoria, 0.0) + monto
        count += 1

    return {
        "month": month,
        "year": year,
        "month_name": MONTH_NAMES.get(month, str(month)),
        "by_category": by_category,
        "total": sum(by_category.values()),
        "count": count,
    }


# --- Pestaña Resumen ---

def ensure_summary_sheet() -> gspread.Worksheet:
    """
    Garantiza que exista la pestaña 'Resumen'.
    Si no existe, la crea con encabezados.
    """
    spreadsheet = _get_spreadsheet()
    titles = [ws.title for ws in spreadsheet.worksheets()]

    if "Resumen" not in titles:
        ws = spreadsheet.add_worksheet(title="Resumen", rows=50, cols=10)
        ws.update("A1:B1", [["Categoría", "Total"]], value_input_option="USER_ENTERED")
        # Escribe las categorías fijas desde A2 para que el gráfico tenga rango estable
        for i, cat in enumerate(_CATEGORIES, start=2):
            ws.update_cell(i, 1, cat)
        return ws

    return spreadsheet.worksheet("Resumen")


def write_summary_to_sheet(month: int, year: int) -> dict:
    """
    Calcula el resumen mensual y lo escribe en la pestaña 'Resumen'.
    Usa rangos fijos por categoría para que el gráfico de torta se auto-actualice.
    Retorna el dict con los datos del resumen.
    """
    summary = get_monthly_summary(month, year)
    ws = ensure_summary_sheet()

    # Actualiza el encabezado con el mes/año actual
    ws.update_cell(1, 2, f"Total — {summary['month_name']} {year}")

    # Escribe los totales en la columna B, fila fija por categoría
    for i, cat in enumerate(_CATEGORIES, start=2):
        total = summary["by_category"].get(cat, 0.0)
        ws.update_cell(i, 2, total)

    return summary
