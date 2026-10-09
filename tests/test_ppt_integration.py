"""End-to-end PPT smoke test against a local deterministic API (no paid calls)."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
import zipfile

import fitz
from test_research import sample_pdf, FakeResearchClient
from backend.services.research_workspace import translate_reading

ROOT = Path(__file__).resolve().parents[1]
MAKER = ROOT / 'backend/standalone_pdf2ppt/ppt_maker'


class ModelHandler(BaseHTTPRequestHandler):
    calls = 0
    def log_message(self, *args): pass
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).calls += 1
        content = request['messages'][-1]['content']
        if isinstance(content, str) and 'narrative slides' in content:
            data = {'slides': [
                {'title': title, 'bullets':['输入数据与评价条件明确。','解释模块职责与证据之间的关系。'], 'speaker_notes':'这里说明研究动机、输入输出、模块之间的连接，以及在相同预算下进行比较的实验条件。该结果只支持论文所述设置，不意味着对所有任务都有效。', 'source_pages':[1], 'position':position}
                for title, position in [('问题与动机','before_figures'),('方法与机制','before_figures'),('证据与局限','after_figures')]]}
        else:
            data = {'slide_title':'方法工作流程','overall_explanation':'输入经过模型处理后，使用同一预算比较评价结果。', 'annotations':[{'label':'输入','description':'原始输入提供需要分析的证据，模型接收数据并输出待评价的结果。','targetX':.3,'targetY':.4},{'label':'评价','description':'使用相同预算和评价标准，避免将额外计算带来的收益误判为方法改进。','targetX':.7,'targetY':.6}], 'speaker_notes':'详细解释输入、模型与评价之间的关系。比较使用相同预算，但仍需核对具体指标和基线。这些备注保留全部机制说明，避免过度压缩到页面中。', 'follow_up_slides':[]}
        body=json.dumps({'id':'fixture','object':'chat.completion','created':1,'model':'fixture-vision','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(data,ensure_ascii=False)}}]}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


@unittest.skipUnless(shutil.which('node') and (MAKER/'node_modules/pptxgenjs').exists(), 'PPT Node dependencies required')
class PPTIntegrationTests(unittest.TestCase):
    def test_narrative_notes_localized_labels_and_resume(self):
        persistent=os.environ.get('PAPERFECT_TEST_ARTIFACTS')
        temporary=tempfile.TemporaryDirectory() if not persistent else None
        root=Path(persistent or temporary.name)
        paper=root/'sample';pdf=paper/'raw/sample.pdf';sample_pdf(pdf)
        (paper/'parsed').mkdir(exist_ok=True);(paper/'images').mkdir(exist_ok=True);(paper/'pptx').mkdir(exist_ok=True)
        md=paper/'parsed/sample_KnowledgeBase.md'
        md.write_text('# 研究背景\n\nFigure 1 shows the method. PDF page 1.\n\n## 方法\n输入、模型与评价。',encoding='utf-8')
        with fitz.open(pdf) as doc: doc[0].get_pixmap().save(paper/'images/Figure_1.png')
        (paper/'images/figures_metadata.json').write_text(json.dumps({'Figure_1.png':1}),encoding='utf-8')
        translate_reading(str(pdf),str(paper/'research/reading'),client=FakeResearchClient())
        server=ThreadingHTTPServer(('127.0.0.1',0),ModelHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            output=paper/'pptx/sample.pptx'
            env={**os.environ,'PAPERFECT_PPT_API_KEY':'fixture-only','PPT_CONCURRENCY':'1'}
            cmd=[shutil.which('node'),str(MAKER/'generate_full_ppt.js'),str(md),str(paper/'images'),str(output),'creative','-','fixture-vision',f'http://127.0.0.1:{server.server_port}/v1','zh']
            result=subprocess.run(cmd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
            mapping=json.loads((paper/'pptx/slide_sync_map.json').read_text())
            self.assertEqual(mapping['n_slides'],4)
            self.assertEqual([s['kind'] for s in mapping['slides']],['narrative','narrative','figure','narrative'])
            with zipfile.ZipFile(output) as archive:
                notes=[n for n in archive.namelist() if n.startswith('ppt/notesSlides/notesSlide') and n.endswith('.xml')]
                self.assertEqual(len(notes),4)
                figure=archive.read('ppt/slides/slide3.xml').decode()
                self.assertIn('输入数据',figure)  # native editable label, not flattened pixels
            before=ModelHandler.calls
            rerun=subprocess.run(cmd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
            self.assertEqual(rerun.returncode,0,rerun.stderr)
            self.assertEqual(ModelHandler.calls,before)  # identical source/provider reuses caches
        finally:
            server.shutdown();server.server_close()
            if temporary: temporary.cleanup()


if __name__=='__main__': unittest.main()
