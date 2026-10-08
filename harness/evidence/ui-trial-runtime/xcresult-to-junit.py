"""Faithful local conversion of exported XCTest leaf results; no test execution."""
import argparse,hashlib,json,re
from pathlib import Path
from xml.etree import ElementTree as ET
p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('source',type=Path);a=p.parse_args()
definitions={'CalculationRegressionTests':'CalculatorTests/CalculationRegressionTests.swift','CalculatorTokensTests':'CalculatorTests/CalculatorTokensTests.swift','CalculatorUITests':'CalculatorUITests/CalculatorUITests.swift'}
native=json.loads((a.run/'tests.json').read_text());summary=json.loads((a.run/'summary.json').read_text())
cases=[]
def walk(rows):
    for row in rows:
        if row['nodeType']=='Test Case':cases.append(row)
        walk(row.get('children',[]))
walk(native['testNodes']);assert len(cases)==summary['totalTestCount']>0
report=ET.Element('testsuite',name='CalculatorSwiftUI',tests=str(len(cases)));mapping=[];counts=dict(passed=0,failed=0,skipped=0)
for row in cases:
    classname,name=row['nodeIdentifier'].split('/');assert row['name']==name
    source=definitions[classname];method=name.removesuffix('()')
    assert re.search(r'func\s+'+re.escape(method)+r'\s*\(', (a.source/source).read_text())
    testcase=ET.SubElement(report,'testcase',classname=classname,name=name,file=str(a.source/source),time=str(row['durationInSeconds']))
    if row['result']=='Passed':status='passed'
    elif row['result']=='Skipped':status='skipped';ET.SubElement(testcase,'skipped',message='XCTest result: Skipped')
    elif row['result']=='Failed':status='failed';ET.SubElement(testcase,'failure',message='XCTest result: Failed; inspect retained xcresult')
    else:raise ValueError('Unsupported native test result: '+row['result'])
    counts[status]+=1
    mapping.append(dict(id=row['nodeIdentifier'],classname=classname,name=name,definition=source,result=status,nodeIdentifierURL=row['nodeIdentifierURL']))
assert counts==dict(passed=summary['passedTests'],failed=summary['failedTests'],skipped=summary['skippedTests'])
assert summary['expectedFailures']==0
report.set('failures',str(counts['failed']));report.set('errors','0');report.set('skipped',str(counts['skipped']))
out=a.run/'junit.xml';assert not out.exists()
out.write_bytes(ET.tostring(report,encoding='utf-8',xml_declaration=True)+b'\n')
record=dict(converter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),tests_json_sha256=hashlib.sha256((a.run/'tests.json').read_bytes()).hexdigest(),summary_json_sha256=hashlib.sha256((a.run/'summary.json').read_bytes()).hexdigest(),report_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),leaf_results=mapping,counts=dict(discovered=len(cases),executed=len(cases)-counts['skipped'],**counts),scope='The native report is retained unchanged. This mapping preserves all leaf results and does not invent tests, native exit status, coverage or human acceptance.')
(a.run/'conversion.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(record['counts'])
