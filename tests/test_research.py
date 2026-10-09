import json
from pathlib import Path
import re
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock
import xml.etree.ElementTree as ET

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import config
from backend.services.model_pick import pick_fast_text_model, pick_parse_model, pick_vision_model
from backend.services.research_workspace import translate_reading, generate_notes, sanitize_html, localized_svg, validate_labels, ResearchClient
from backend.api import config_router, research_router


def sample_pdf(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as doc:
        for n in (1, 2):
            page = doc.new_page(width=600, height=800)
            page.insert_text((40, 40), f"Page {n}. The method improves accuracy under equal budgets.")
            page.draw_rect(fitz.Rect(60, 150, 480, 340), color=(0, .5, .5))
            page.insert_text((90, 220), "Input data -> Model -> Evaluation")
        doc.save(path)


class FakeResearchClient:
    def __init__(self, fail_page=None):
        self.fail_page = fail_page

    def json(self, skill, content, cache, force=False, validate=None):
        if 'FIGURE LOCALIZATION ONLY' in skill:
            return {"labels": [{"source":"Input data", "text":"输入数据", "bbox":[70,320,195,385], "background":"#ffffff", "color":"#172b3a", "rotation":0}], "warnings":[]}
        if isinstance(content, list):
            n = int(re.search(r'physical PDF page (\d+)', content[0]['text'])[1])
            if n == self.fail_page:
                raise RuntimeError('fixture unavailable')
            return {"page":n, "html":'<h2>研究方法</h2><p>在相同预算下比较准确率。</p><table><tr><th>条件</th><td>42.5 ± 0.2</td></tr></table><figure><asset id="fig1"></asset><figcaption>图1：输入、模型与评价。</figcaption></figure>', "crops":[{"id":"fig1","kind":"figure","bbox":[100,180,800,430],"label":f"Figure {n}"}], "warnings":[]}
        return {"summary":"说明问题、方法和实验条件。", "sections":[{"title":"方法与证据", "text":"方法在相同预算下进行比较，不能据此推断其他条件下仍然有效。", "pages":[1,2]}], "evidence":[{"claim":"Equal budgets", "page":1,"quote":"under equal budgets"},{"claim":"Unsupported", "page":2,"quote":"invented evidence"}], "uncertainties":["图表尚未视觉核查"]}


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'.env'
        self.patch=patch.object(config,'ENV_PATH',str(self.path)); self.patch.start()
    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def test_roundtrip_independent_providers_and_key_lists(self):
        config.save_config({'parse_api_url':'https://example.test/v1/', 'parse_model':'custom-reasoner', 'parse_api_key':['first','second'], 'ppt_api_url':'http://localhost:9000/v1','ppt_model':'custom-vision','ppt_api_key':'local'})
        c=config.load_config(for_settings=True)
        self.assertEqual(c['parse_api_key'],['first','second'])
        self.assertEqual(c['parse_api_url'],'https://example.test/v1')
        self.assertEqual(pick_parse_model(c),'custom-reasoner')
        self.assertEqual(pick_vision_model(c),'custom-vision')
        self.assertEqual(pick_fast_text_model({'chat_model':'heavy-vision-72b'},stage='chat'),'heavy-vision-72b')

    def test_legacy_keys_and_no_cross_provider_inheritance(self):
        config.save_config({'parse_api_key':'old-key'})
        self.assertEqual(config.load_config()['ppt_api_key'],'old-key')
        config.save_config({'ppt_api_url':'https://different.test/v1'})
        self.assertEqual(config.load_config()['ppt_api_key'],'')

    def test_invalid_request_does_not_partially_write(self):
        config.save_config({'chat_model':'before'})
        before=self.path.read_bytes()
        for bad in [{'chat_model':'after','paper_api_url':'javascript:alert(1)'},{'arbitrary':'value'},{'chat_model':'a\nB=secret'},{'chat_api_url':'https://a.test/v1/responses'}]:
            with self.assertRaises(ValueError): config.save_config(bad)
            self.assertEqual(self.path.read_bytes(),before)

    def test_http_settings_validation(self):
        app=FastAPI();app.include_router(config_router.router)
        client=TestClient(app)
        self.assertEqual(client.post('/api/config',json={'chat_model':'mine'}).status_code,200)
        self.assertEqual(client.get('/api/config').json()['chat_model'],'mine')
        self.assertEqual(client.post('/api/config',json={'chat_api_url':'file:///private'}).status_code,422)


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.pdf=self.root/'source.pdf';sample_pdf(self.pdf)
    def tearDown(self): self.temp.cleanup()

    def test_translation_exports_editable_svg_and_tables(self):
        result=translate_reading(str(self.pdf),str(self.root/'reading'),client=FakeResearchClient())
        self.assertEqual(result['completed_pages'],[1,2]);self.assertEqual(result['status'],'complete')
        content=Path(result['html_path']).read_text(encoding='utf-8')
        self.assertIn('<table>',content);self.assertIn('42.5 ± 0.2',content)
        asset=result['figures'][0]
        root=ET.fromstring((self.root/'reading'/asset['localized_svg']).read_text(encoding='utf-8'))
        self.assertTrue(root.findall('{http://www.w3.org/2000/svg}image'))
        self.assertTrue(root.findall('.//{http://www.w3.org/2000/svg}text'))
        self.assertTrue((self.root/'reading'/asset['original_svg']).is_file())

    def test_page_failure_is_partial_and_keeps_original(self):
        result=translate_reading(str(self.pdf),str(self.root/'reading'),client=FakeResearchClient(fail_page=2))
        self.assertEqual(result['status'],'partial');self.assertEqual(result['completed_pages'],[1])
        self.assertIn('The method improves accuracy',Path(result['html_path']).read_text(encoding='utf-8'))

    def test_scope_and_evidence_validation(self):
        result=translate_reading(str(self.pdf),str(self.root/'reading'),pages=[2],client=FakeResearchClient())
        self.assertEqual(result['selected_pages'],[2])
        with self.assertRaises(ValueError): translate_reading(str(self.pdf),str(self.root/'reading'),pages=[99],client=FakeResearchClient())
        notes=generate_notes(str(self.pdf),str(self.root/'notes'),client=FakeResearchClient())
        self.assertEqual(notes['pages_covered'],[1,2])
        self.assertEqual([e['quote_found_on_page'] for e in notes['evidence']],[True,False])
        self.assertEqual(notes['status'],'draft')

    def test_generated_markup_cannot_execute_or_fetch(self):
        clean=sanitize_html('<script>alert(1)</script><img src="https://bad.test"><p onclick="x()">safe</p><table><td colspan="2" style="x">42</td></table>',{})
        self.assertNotIn('<script',clean);self.assertNotIn('<img',clean);self.assertNotIn('onclick',clean)
        self.assertIn('colspan="2"',clean)
        with self.assertRaises(ValueError): validate_labels({'labels':[{'bbox':[0,0,1001,5]}]})

    def test_file_routes_confine_artifacts(self):
        directory=self.root/'data/papers/sample'
        sample_pdf(directory/'raw/sample.pdf')
        (directory/'research/reading').mkdir(parents=True)
        (directory/'research/reading/index.html').write_text('<p>result</p>',encoding='utf-8')
        app=FastAPI();app.include_router(research_router.router)
        with patch.object(research_router,'get_base_dir',return_value=str(self.root)):
            client=TestClient(app)
            response=client.get('/api/research/sample/files/reading/index.html')
            self.assertEqual(response.status_code,200);self.assertIn("sandbox",response.headers['content-security-policy'])
            with self.assertRaises(Exception): research_router.research_file('sample','../../raw/sample.pdf')

    def test_response_cache_changes_with_model_and_rejects_truncation(self):
        response=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='{"summary":"verified fixture"}'))],usage=None)
        create=Mock(return_value=response)
        client=ResearchClient.__new__(ResearchClient)
        client.model='model-a';client.url='http://fixture/v1'
        client.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        cache=self.root/'cache.json'
        client.json('skill','input',cache)
        client.json('skill','input',cache)
        self.assertEqual(create.call_count,1)
        client.model='model-b';client.json('skill','input',cache)
        self.assertEqual(create.call_count,2)
        before=cache.read_bytes()
        response.choices[0].finish_reason='length'
        with self.assertRaises(ValueError): client.json('skill','new input',cache)
        self.assertEqual(cache.read_bytes(),before)

    def test_failed_validation_does_not_poison_cache(self):
        create=Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='{"html":"missing page"}'))],usage=None))
        client=ResearchClient.__new__(ResearchClient)
        client.model='fixture';client.url='http://fixture/v1';client.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        from backend.services.research_workspace import validate_page
        cache=self.root/'invalid.json'
        with self.assertRaises(ValueError): client.json('skill','input',cache,validate=lambda data:validate_page(data,1))
        self.assertFalse(cache.exists())


if __name__=='__main__': unittest.main()
