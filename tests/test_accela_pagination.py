import unittest

from tampa_accela.client import CollectionError, next_page_target, parse_result_rows


def page(rows, next_target=None, headers=("Record Number", "Record Type", "Status", "Date", "Address")):
    head = "".join(f"<th>{value}</th>" for value in headers)
    body = "".join(
        "<tr>" + "".join(
            f'<td><a href="Cap/CapDetail.aspx?capID1={number}&amp;capID2=B&amp;capID3=C">{value}</a></td>' if index == 0 else f"<td>{value}</td>"
            for index, value in enumerate(values)
        ) + "</tr>"
        for number, values in rows
    )
    link = f'<a href="javascript:__doPostBack(\'{next_target}\',\'\')">Next &gt;</a>' if next_target else ""
    return f'<table id="ctl00_PlaceHolderMain_dgvPermitList_gdvPermitList"><tr>{head}</tr>{body}</table>{link}'


class PaginationParsingTests(unittest.TestCase):
    def test_rows_and_dynamic_next_target(self):
        html = page([("A", ("A", "Building", "Open", "08/13/2026", "1 MAIN ST"))], "dgvPermitList$ctl13$ctl14")
        html = html.replace("<tr>", "<tr><td>Showing 1-10 of 100+</td></tr><tr>", 1)
        rows = parse_result_rows(html, "https://aca.test/TAMPA/")
        self.assertEqual(rows[0]["Record Number"], "A")
        self.assertIn("capID1=A", rows[0]["_source_url"])
        self.assertEqual(next_page_target(html), "dgvPermitList$ctl13$ctl14")

    def test_empty_and_changing_schema_are_deterministic(self):
        self.assertEqual(parse_result_rows("<p>No records found</p>", "https://aca.test/"), [])
        html = page([("A", ("A", "Open"))], headers=("Record Number", "Status"))
        self.assertEqual(parse_result_rows(html, "https://aca.test/")[0]["Status"], "Open")

    def test_malformed_row_is_skipped(self):
        html = '<table id="x_dgvPermitList_gdvPermitList"><tr><th>Record Number</th><th>Status</th></tr><tr><td>A</td></tr></table>'
        self.assertEqual(parse_result_rows(html, "https://aca.test/"), [])


if __name__ == "__main__":
    unittest.main()
