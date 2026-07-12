import io
import unittest

from payroll_app.pdf_utils import build_pdf_from_rows


class PdfUtilsTests(unittest.TestCase):
    def test_build_pdf_from_rows_returns_pdf_bytes(self):
        pdf_bytes = build_pdf_from_rows(
            title='Prueba PDF',
            rows=[('Encabezado', 'Valor')],
            metadata={'Periodo': '2024-01-01 a 2024-01-31'},
        )

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))


if __name__ == '__main__':
    unittest.main()
