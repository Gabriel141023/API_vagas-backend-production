from flask import Flask, jsonify, request
import requests
import re
import os
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

import sqlite3  
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    USE_POSTGRES = True
except ImportError:
    USE_POSTGRES = False

app = Flask(__name__)

# ============ CONFIGURAÇÃO DO BANCO ============
DATABASE_URL = os.environ.get('DATABASE_URL')  # Render injeta automaticamente

if not DATABASE_URL:
    DATABASE_URL = 'sqlite:///vagas_devjr.db'  # Fallback local
    USE_POSTGRES = False

def get_db():
    """Retorna conexão PostgreSQL ou SQLite"""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    else:
        conn = sqlite3.connect('vagas_devjr.db')
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    """Cria tabela no PostgreSQL ou SQLite"""
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vagas (
                id SERIAL PRIMARY KEY,
                empresa TEXT NOT NULL,
                cargo TEXT NOT NULL,
                salario TEXT,
                link TEXT UNIQUE,
                palavras_chave TEXT,
                data_postagem TEXT,
                localizacao TEXT,
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vagas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa TEXT NOT NULL,
                cargo TEXT NOT NULL,
                salario TEXT,
                link TEXT UNIQUE,
                palavras_chave TEXT,
                data_postagem TEXT,
                localizacao TEXT,
                data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    
    conn.commit()
    cursor.close()
    conn.close()
    
    db_tipo = "PostgreSQL" if USE_POSTGRES else "SQLite"
    print(f"✅ Banco {db_tipo} inicializado!")

# Inicializa ao importar
init_db()

# ============ ROTAS ============

@app.route('/')
def home():
    return jsonify({
        "message": "API de Vagas Backend Brasil",
        "banco": "PostgreSQL" if USE_POSTGRES else "SQLite",
        "endpoints": {
            "listar": "/vagas",
            "buscar": "/vagas/buscar/<palavra>",
            "scraping": "/scraping/backend-br"
        }
    })

@app.route('/vagas')
def listar_vagas():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vagas ORDER BY data_postagem DESC LIMIT 50")
        vagas = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify([dict(vaga) for vaga in vagas])
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/vagas/buscar/<palavra>')
def buscar_palavra(palavra):
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            cursor.execute("""
                SELECT * FROM vagas
                WHERE cargo ILIKE %s OR palavras_chave ILIKE %s OR empresa ILIKE %s
                ORDER BY data_postagem DESC
            """, (f'%{palavra}%', f'%{palavra}%', f'%{palavra}%'))
        else:
            cursor.execute("""
                SELECT * FROM vagas
                WHERE cargo LIKE ? OR palavras_chave LIKE ? OR empresa LIKE ?
                ORDER BY data_postagem DESC
            """, (f'%{palavra}%', f'%{palavra}%', f'%{palavra}%'))
        
        vagas = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify([dict(vaga) for vaga in vagas])
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# ============ SCRAPING ============
@app.route('/scraping/backend-br', methods=['GET'])
def scrape_backend_br():
    url = "https://api.github.com/repos/backend-br/vagas/issues"
    
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'Flask-Job-Scraper-BR/1.0'
    }
    
    params = {
        'state': 'open',
        'per_page': 50,
        'sort': 'created',
        'direction': 'desc'
    }
    
    try:
        print("🔍 Buscando issues no GitHub...")
        response = requests.get(url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        issues = response.json()
        
        print(f"📥 Recebidas {len(issues)} issues")
        
        conn = get_db()
        cursor = conn.cursor()
        total_salvas = 0
        vagas_exemplo = []
        
        for idx, issue in enumerate(issues, 1):
            try:
                titulo = issue.get('title', 'Sem título')
                corpo = issue.get('body', '')
                link = issue.get('html_url', '')
                data_postagem = issue.get('created_at', '')[:10]
                
                # Extrai empresa
                empresa = 'Não especificada'
                match_empresa = re.search(r'\[([^\]]+)\]', titulo)
                if match_empresa:
                    possivel = match_empresa.group(1)
                    if possivel.lower() not in ['remoto', 'híbrido', 'presencial', 'sp', 'rj']:
                        empresa = possivel
                
                # Cargo
                cargo = re.sub(r'\[.*?\]\s*', '', titulo).strip() or titulo
                
                # Localização
                localizacao = 'Não especificado'
                if any(w in titulo.lower() for w in ['remoto', 'remote']):
                    localizacao = 'Remoto'
                elif 'híbrido' in titulo.lower():
                    localizacao = 'Híbrido'
                
                # Salário
                salario = 'Não informado'
                if corpo:
                    match_sal = re.search(r'R\$\s*[\d.,]+(?:\s*[-ka]\s*[\d.,]+)?', corpo, re.I)
                    if match_sal:
                        salario = match_sal.group(0)
                
                # Tecnologias
                tech_list = ['Python', 'Django', 'Flask', 'FastAPI', 'Java', 'Node',
                            'TypeScript', 'JavaScript', 'Go', 'Ruby', 'PHP', 'Docker',
                            'AWS', 'PostgreSQL', 'MongoDB', 'Redis', 'Backend']
                
                texto = (titulo + ' ' + corpo).lower()
                techs = [t for t in tech_list if t.lower() in texto]
                palavras_chave = ', '.join(set(techs[:8])) or 'backend'
                
                # INSERT compatível com PostgreSQL e SQLite
                if USE_POSTGRES:
                    cursor.execute('''
                        INSERT INTO vagas (empresa, cargo, salario, link, palavras_chave, data_postagem, localizacao) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (link) DO NOTHING
                    ''', (empresa[:100], cargo[:250], salario[:100], link[:500], 
                          palavras_chave[:250], data_postagem, localizacao[:100]))
                else:
                    cursor.execute('''
                        INSERT OR IGNORE INTO vagas (empresa, cargo, salario, link, palavras_chave, data_postagem, localizacao) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (empresa[:100], cargo[:250], salario[:100], link[:500], 
                          palavras_chave[:250], data_postagem, localizacao[:100]))
                
                if cursor.rowcount > 0:
                    total_salvas += 1
                    if len(vagas_exemplo) < 5:
                        vagas_exemplo.append({"empresa": empresa, "cargo": cargo[:60]})
                
            except Exception as e:
                print(f"Erro issue #{idx}: {e}")
                continue
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            "message": f"✅ {total_salvas} vagas salvas!",
            "total_analisadas": len(issues),
            "vagas_exemplo": vagas_exemplo,
            "banco": "PostgreSQL" if USE_POSTGRES else "SQLite"
        })
        
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 API VAGAS - BACKEND BRASIL")
    print(f"📊 Banco: {'PostgreSQL' if USE_POSTGRES else 'SQLite'}")
    print("=" * 70)
    app.run(debug=True)
