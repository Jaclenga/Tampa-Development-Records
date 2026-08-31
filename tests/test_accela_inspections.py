import unittest

from tampa_accela.client import next_inspection_page_target, parse_inspection_rows


SAMPLE = """
<table id="ctl00_PlaceHolderMain_InspectionList_gvListCompleted">
  <tr class="InspectionListRow"><td><table><tr><td>
    <span style="font-weight:bold">Approved</span>
    <span>BLD-Final</span><br><span>Result by: Jane Doe on 04/16/2026</span>
  </td><td><a onclick="showInspectionPopupDialog('/TAMPA/Inspection/InspectionDetails.aspx?agencyCode=TAMPA&amp;ID=4453216&amp;isPopup=Y')">View Details</a></td></tr></table></td></tr>
  <tr class="ACA_Table_Pages"><td><a href="javascript:__doPostBack(&#39;ctl00$PlaceHolderMain$InspectionList$gvListCompleted$ctl08$ctl09&#39;,&#39;&#39;)">Next &gt;</a></td></tr>
</table>
"""


class AccelaInspectionParserTests(unittest.TestCase):
    def test_parses_presentation_row_and_detail_identifier(self):
        self.assertEqual(parse_inspection_rows(SAMPLE), [{
            "Inspection Type": "BLD-Final",
            "Status": "Approved",
            "Inspection ID": "4453216",
            "Result": "Approved",
            "Inspector": "Jane Doe",
            "Result Date": "04/16/2026",
        }])

    def test_finds_completed_next_target(self):
        self.assertEqual(
            next_inspection_page_target(SAMPLE, "completed"),
            "ctl00$PlaceHolderMain$InspectionList$gvListCompleted$ctl08$ctl09",
        )
        self.assertIsNone(next_inspection_page_target(SAMPLE, "upcoming"))

    def test_empty_layout_does_not_emit_an_observation(self):
        source = '<table id="ctl00_PlaceHolderMain_InspectionList_gvListCompleted"><tr><td>There are no completed inspections on this record.</td></tr></table>'
        self.assertEqual(parse_inspection_rows(source), [])


if __name__ == "__main__":
    unittest.main()
