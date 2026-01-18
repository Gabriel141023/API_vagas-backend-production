from flask import Flask, jsonify, request
import sqlite3
from datetime import datetime
import requests
import re
import os

app = Flask(__name__)
DATABASE = 'vagas_devjr.db'


# ============ CRIA BANCO COM SCHEMA CORRETO ============
def init_db():
    """Cria banco com as colunas certas"""
    conn = sqlite3.connect(DATABASE)
    conn.execute('''CREATE TABLE IF NOT EXISTS vagas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa TEXT NOT NULL,
        cargo TEXT NOT NULL,
        salario TEXT,
        link TEXT UNIQUE,
        palavras_chave TEXT,
        data_postagem TEXT,
        localizacao TEXT,
        data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()
    print("✅ Banco criado com schema correto!")

# Inicializa banco ao iniciar
init_db()

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ============ ROTAS ============

@app.route('/vagas')
def listar_vagas():
    try:
        conn = get_db()
        vagas = conn.execute("SELECT * FROM vagas ORDER BY data_postagem DESC LIMIT 50").fetchall()
        conn.close()
        return jsonify([dict(vaga) for vaga in vagas])
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/vagas/python', methods=['GET'])
def vagas_python():
    """Filtra vagas Python"""
    conn = get_db()
    vagas = conn.execute("""
        SELECT * FROM vagas 
        WHERE cargo LIKE '%python%' OR palavras_chave LIKE '%python%' 
        ORDER BY data_cadastro DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(v) for v in vagas])

@app.route('/vagas/buscar/<palavra>')
def buscar_palavra(palavra):
    try:
        conn = get_db()
        vagas = conn.execute("""
            SELECT * FROM vagas
            WHERE cargo LIKE ? OR palavras_chave LIKE ? OR empresa LIKE ?
            ORDER BY data_postagem DESC
        """, (f'%{palavra}%', f'%{palavra}%', f'%{palavra}%')).fetchall()
        conn.close()
        return jsonify([dict(vaga) for vaga in vagas])
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# ============ SCRAPING ============
@app.route('/scraping/backend-br', methods=['GET'])
def scrape_backend_br():
    """Busca issues do backend-br/vagas"""
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
        
        print(f"📥 Recebidas {len(issues)} issues da API")
        
        if not issues:
            return jsonify({"erro": "API retornou lista vazia"}), 404
        
        conn = get_db()
        total_salvas = 0
        erros = []
        vagas_exemplo = []
        
        for idx, issue in enumerate(issues, 1):
            try:
                titulo_completo = issue.get('title', 'Sem título')
                corpo = issue.get('body', '')
                link = issue.get('html_url', '')
                data_postagem = issue.get('created_at', '')[:10]
                
                print(f"\n📋 Issue #{idx}: {titulo_completo[:60]}...")
                
                # Extrai empresa
                empresa = 'Não especificada'
                match_empresa = re.search(r'\[([^\]]+)\]', titulo_completo)
                if match_empresa:
                    possivel_empresa = match_empresa.group(1)
                    if possivel_empresa.lower() not in ['remoto', 'híbrido', 'presencial', 'sp', 'rj', 'brasil']:
                        empresa = possivel_empresa
                
                # Cargo = título sem colchetes
                cargo = re.sub(r'\[.*?\]\s*', '', titulo_completo).strip()
                if not cargo:
                    cargo = titulo_completo
                
                # Localização
                localizacao = 'Não especificado'
                if any(word in titulo_completo.lower() for word in ['remoto', 'remote']):
                    localizacao = 'Remoto'
                elif 'híbrido' in titulo_completo.lower():
                    localizacao = 'Híbrido'
                
                # Salário
                salario = 'Não informado'
                if corpo:
                    match_salario = re.search(r'R\$\s*[\d.,]+(?:\s*[-ka]\s*[\d.,]+)?', corpo, re.IGNORECASE)
                    if match_salario:
                        salario = match_salario.group(0)
                
                # Palavras-chave
                tech_list = ['Python', 'Django', 'Flask', 'FastAPI', 'Java', 'Node', 
                            'TypeScript', 'JavaScript', 'Go', 'Ruby', 'PHP', 'Docker',
                            'AWS', 'PostgreSQL', 'MongoDB', 'Redis', 'Backend']
                
                texto_completo = (titulo_completo + ' ' + corpo).lower()
                tech_encontradas = [tech for tech in tech_list if tech.lower() in texto_completo]
                palavras_chave = ', '.join(set(tech_encontradas[:8])) or 'backend'
                
                # INSERE NO BANCO
                try:
                    conn.execute('''INSERT OR IGNORE INTO vagas 
                        (empresa, cargo, salario, link, palavras_chave, data_postagem, localizacao) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                        (
                            empresa[:100],
                            cargo[:250],
                            salario[:100],
                            link[:500],
                            palavras_chave[:250],
                            data_postagem,
                            localizacao[:100]
                        )
                    )
                    conn.commit()
                    total_salvas += 1
                    
                    if len(vagas_exemplo) < 5:
                        vagas_exemplo.append({
                            "empresa": empresa,
                            "cargo": cargo[:80],
                            "localizacao": localizacao
                        })
                    
                    print(f"   ✅ SALVA: {empresa} - {cargo[:50]}")
                    
                except sqlite3.IntegrityError:
                    print(f"   ⚠️ Duplicada")
                except Exception as db_err:
                    print(f"   ❌ Erro DB: {db_err}")
                    erros.append(f"Issue #{idx}: {str(db_err)}")
                
            except Exception as e:
                erros.append(f"Issue #{idx}: {str(e)}")
                continue
        
        conn.close()
        
        return jsonify({
            "message": f"✅ {total_salvas} vagas salvas!",
            "vagas_salvas": total_salvas,
            "vagas_exemplo": vagas_exemplo,
            "link_fonte": "https://github.com/backend-br/vagas/issues"
        })
        
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# ============ DEBUG ============
@app.route('/debug/github-raw', methods=['GET'])
def debug_github():
    """Ver issues brutas do GitHub"""
    url = "https://api.github.com/repos/backend-br/vagas/issues"
    
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'Flask-Job-Scraper-BR/1.0'
    }
    
    params = {'state': 'open', 'per_page': 10}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        issues = response.json()
        
        resumo = []
        for i, issue in enumerate(issues[:10], 1):
            resumo.append({
                "numero": i,
                "titulo": issue.get('title', 'N/A'),
                "link": issue.get('html_url', 'N/A')
            })
        
        return jsonify({"total_issues": len(issues), "primeiras_10": resumo})
        
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 API VAGAS - BACKEND BRASIL")
    print("=" * 70)
    print("\n📊 Endpoints:")
    print("   GET /vagas")
    print("   GET /vagas/buscar/Python")
    print("   GET /scraping/backend-br")
    print("\n🌐 http://127.0.0.1:5000")
    print("=" * 70)
    app.run(debug=True)
