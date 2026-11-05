import unittest, tempfile
from pathlib import Path
import app as mod
class TestApp(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old=mod.DB
        mod.DB=Path(self.temp.name)/'test.db'
        mod.init_db()
        self.client=mod.app.test_client()
    def tearDown(self):
        mod.DB=self.old
        self.temp.cleanup()
    def test_cadastro_e_api(self):
        r=self.client.post('/novo',data={'nome':'Luna','sexo':'Fêmea','idade':'2 anos','status':'Disponível para adoção'})
        self.assertEqual(r.status_code,302)
        a=self.client.get('/api/animais').get_json()
        self.assertEqual(a[0]['nome'],'Luna')
        self.assertNotIn('observacoes',a[0])
    def test_status_remove_da_vitrine(self):
        self.client.post('/novo',data={'nome':'Thor','status':'Disponível para adoção'})
        self.assertEqual(len(self.client.get('/api/animais').get_json()),1)
        self.client.post('/animal/1/status',data={'status':'Adotado'})
        self.assertEqual(len(self.client.get('/api/animais').get_json()),0)
    def test_paginas(self):
        for route in ('/','/novo','/tratamento','/adocao'):
            self.assertEqual(self.client.get(route).status_code,200)
if __name__=='__main__': unittest.main()
