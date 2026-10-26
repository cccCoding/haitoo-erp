"""财务异常订单导出；订单号和 SKU 始终作为文本写入。"""
from io import BytesIO
from urllib.parse import quote
from unicodedata import east_asian_width

from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


def export_workbook(filename, sheets):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, headers, records in sheets:
        sheet = workbook.create_sheet(name)
        sheet.append(headers)
        for index, record in enumerate(records, start=2):
            sheet.append(record)
            # 表格中的文本只是数据，即使以 = 开头也不能成为 Excel 公式。
            for cell in sheet[index]:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
                elif isinstance(cell.value, (int, float)) or cell.data_type == 'n':
                    if cell.value is not None:
                        cell.number_format = '#,##0.00' if not isinstance(cell.value, int) else '#,##0'
                elif cell.data_type == 'd':
                    cell.number_format = 'yyyy-mm-dd hh:mm:ss'
        for cell in sheet[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='6043D4')
        sheet.freeze_panes = 'A2'
        sheet.row_dimensions[1].height = 24
        sheet.auto_filter.ref = sheet.dimensions
        def display_width(value):
            return sum(2 if east_asian_width(char) in 'WF' else 1 for char in str(value or ''))
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(48, max(18,
                max(display_width(cell.value) for cell in column) + 3))
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return Response(output.getvalue(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}", 'Cache-Control': 'no-store'})
