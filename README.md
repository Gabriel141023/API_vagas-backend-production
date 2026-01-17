# API Vagas Backend Brasil

Busca vagas reais de desenvolvedor backend no Brasil via GitHub Issues do repositório backend-br/vagas.

## 🔗 Endpoints Disponíveis

- `GET /vagas` - Lista todas as vagas (últimas 50)
- `GET /vagas/python` - Filtra vagas Python
- `GET /vagas/buscar/<palavra>` - Busca customizada (ex: `/vagas/buscar/Java`)
- `GET /scraping/backend-br` - Atualiza vagas do GitHub

## Stack

- **Backend**: Flask 3.0
- **Database**: SQLite3
- **Scraping**: GitHub API REST
- **Deploy**: Gunicorn

## Dados

Fonte: [backend-br/vagas](https://github.com/backend-br/vagas/issues)

Última atualização: Janeiro 2026

## Rodar Localmente

```bash
pip install -r requirements.txt
python Api_vagas.py
