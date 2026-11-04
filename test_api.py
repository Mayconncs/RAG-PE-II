"""Contrato da API, sem downloads de modelos nem chamadas ao OpenRouter."""
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import api


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    def test_missing_key(self):
        with patch.object(api, 'API_KEY', None):
            self.assertEqual(self.client.post('/api/chat', json={'pergunta': 'Olá'}).status_code, 503)

    def test_validation(self):
        for dados in ({'pergunta': ''}, {'pergunta': ' '}, {'pergunta': 'x'*4001}, {'pergunta': 'oi', 'historico': [{'pergunta': 'a', 'resposta': 'b'}]*3}):
            self.assertEqual(self.client.post('/api/chat', json=dados).status_code, 422)

    def test_answer_and_follow_up(self):
        fonte = dict(ato='Lei', artigos='Art. 1', fonte='a.pdf', paginas='1', content='Trecho', vector=[1], _i=0)
        with patch.object(api, 'API_KEY', 'teste'), patch.object(api, 'recuperar', return_value=([fonte], [], '')) as busca, patch.object(api, 'responder', return_value=('Resposta.', 'teste', None)), patch.object(api, 'montar_pergunta', return_value='prompt') as prompt:
            r = self.client.post('/api/chat', json={'pergunta': 'e ele?', 'historico': [{'pergunta': 'Plantão', 'resposta': 'Resposta anterior'}]})
            self.assertEqual(r.status_code, 200)
            busca.assert_called_once_with('Plantão e ele?')
            self.assertEqual(prompt.call_args.args[1], [('Plantão', 'Resposta anterior')])
            self.assertNotIn('vector', r.json()['fontes'][0])
            self.assertNotIn('_i', r.json()['fontes'][0])

    def test_provider_failure(self):
        with patch.object(api, 'API_KEY', 'teste'), patch.object(api, 'recuperar', return_value=([], [], '')), patch.object(api, 'responder', return_value=(None, None, 'Indisponível')):
            r = self.client.post('/api/chat', json={'pergunta': 'Teste'})
            self.assertEqual(r.status_code, 502)

    def test_pdf_source_and_invalid_paths(self):
        from config import PASTA_PDFS
        pdf = next(PASTA_PDFS.glob('*.pdf'))
        r = self.client.get('/api/fontes/' + pdf.name)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers['content-type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))
        for arquivo in ('inexistente.pdf', '.env', '..%5Csegredo.pdf'):
            self.assertEqual(self.client.get('/api/fontes/' + arquivo).status_code, 404)

    def test_busy(self):
        with patch.object(api, 'API_KEY', 'teste'):
            api._consulta_lock.acquire()
            try:
                self.assertEqual(self.client.post('/api/chat', json={'pergunta': 'Teste'}).status_code, 429)
            finally:
                api._consulta_lock.release()

    def test_static_page_and_status(self):
        if not api.dist.is_dir():
            self.skipTest('Compile o frontend para testar a página estática.')
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Consulta', r.text)

    def test_status_without_database(self):
        with patch.object(api.lancedb, 'connect', side_effect=ValueError('ausente')):
            r = self.client.get('/api/status')
            self.assertFalse(r.json()['base_pronta'])


if __name__ == '__main__':
    unittest.main()
