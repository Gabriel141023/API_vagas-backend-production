from flask import Flask, jsonify, request
import sqlite3
from datetime import datetime
import requests
import re

app = Flask(__name__)
DATABASE = 'vagas_devjr.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
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

@app.route('/initdb', methods=['GET'])
def init():
    init_db()
    return jsonify({"message": "✅ Tabela criada!"})

@app.route('/vagas', methods=['GET'])
def listar_vagas():
    """Lista todas as vagas"""
    conn = get_db()
    vagas = conn.execute(
        'SELECT * FROM vagas ORDER BY data_cadastro DESC LIMIT 50'
    ).fetchall()
    conn.close()
    return jsonify([dict(v) for v in vagas])

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

@app.route('/vagas/buscar/<palavra>', methods=['GET'])
def buscar_palavra(palavra):
    """Busca vagas por palavra-chave específica"""
    conn = get_db()
    vagas = conn.execute("""
        SELECT * FROM vagas 
        WHERE cargo LIKE ? OR palavras_chave LIKE ? OR empresa LIKE ?
        ORDER BY data_cadastro DESC
    """, (f'%{palavra}%', f'%{palavra}%', f'%{palavra}%')).fetchall()
    conn.close()
    return jsonify({
        "total": len(vagas),
        "palavra_buscada": palavra,
        "vagas": [dict(v) for v in vagas]
    })

@app.route('/fix-db', methods=['GET'])
def fix_database():
    """Adiciona coluna localizacao na tabela existente"""
    try:
        conn = get_db()
        cursor = conn.execute("PRAGMA table_info(vagas)")
        colunas = [row[1] for row in cursor.fetchall()]
        
        if 'localizacao' not in colunas:
            conn.execute('ALTER TABLE vagas ADD COLUMN localizacao TEXT')
            conn.commit()
            message = "✅ Coluna 'localizacao' adicionada!"
        else:
            message = "⚠️ Coluna já existe"
        
        conn.close()
        return jsonify({"message": message})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/reset-db', methods=['GET'])
def reset_database():
    """⚠️ APAGA banco e recria do zero"""
    import os
    try:
        if os.path.exists(DATABASE):
            os.remove(DATABASE)
        init_db()
        return jsonify({
            "message": "✅ Banco recriado!",
            "aviso": "Vagas antigas apagadas"
        })
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
# ============ SCRAPING SIMPLIFICADO - SEM FILTROS COMPLEXOS ============
@app.route('/scraping/backend-br', methods=['GET'])
def scrape_backend_br():
    """
    Busca TODAS as issues abertas do backend-br/vagas
    SALVA TUDO sem filtros - depois você filtra no banco
    """
    url = "https://api.github.com/repos/backend-br/vagas/issues"
    
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'Flask-Job-Scraper-BR/1.0'
    }
    
    params = {
        'state': 'open',
        'per_page': 50,  # Aumentado para 50
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
            return jsonify({
                "erro": "API retornou lista vazia",
                "url": url
            }), 404
        
        conn = get_db()
        total_salvas = 0
        erros = []
        vagas_exemplo = []
        
        for idx, issue in enumerate(issues, 1):
            try:
                # EXTRAÇÃO SIMPLES - salva o título completo como cargo
                titulo_completo = issue.get('title', 'Sem título')
                corpo = issue.get('body', '')
                link = issue.get('html_url', '')
                data_postagem = issue.get('created_at', '')[:10]
                
                print(f"\n📋 Issue #{idx}: {titulo_completo[:60]}...")
                
                # Extrai empresa (primeiro texto entre colchetes)
                empresa = 'Não especificada'
                match_empresa = re.search(r'\[([^\]]+)\]', titulo_completo)
                if match_empresa:
                    possivel_empresa = match_empresa.group(1)
                    # Se não for localização, é empresa
                    if possivel_empresa.lower() not in ['remoto', 'híbrido', 'presencial', 'sp', 'rj', 'brasil']:
                        empresa = possivel_empresa
                
                # Cargo = título sem os colchetes
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
                
                # Palavras-chave do título e corpo
                tech_encontradas = []
                tech_list = ['Python', 'Django', 'Flask', 'FastAPI', 'Java', 'Node', 
                            'TypeScript', 'JavaScript', 'Go', 'Ruby', 'PHP', 'Docker',
                            'AWS', 'PostgreSQL', 'MongoDB', 'Redis', 'Backend', 'Desenvolvedor']
                
                texto_completo = (titulo_completo + ' ' + corpo).lower()
                for tech in tech_list:
                    if tech.lower() in texto_completo:
                        tech_encontradas.append(tech.lower())
                
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
                    print(f"   ⚠️ Duplicada (link já existe)")
                except Exception as db_err:
                    print(f"   ❌ Erro DB: {db_err}")
                    erros.append(f"Issue #{idx}: {str(db_err)}")
                
            except Exception as e:
                erros.append(f"Issue #{idx}: {str(e)}")
                print(f"   ❌ Erro ao processar: {e}")
                continue
        
        conn.close()
        
        return jsonify({
            "message": f"✅ {total_salvas} vagas salvas de {len(issues)} issues!",
            "fonte": "backend-br/vagas (GitHub)",
            "total_issues_analisadas": len(issues),
            "vagas_salvas": total_salvas,
            "vagas_exemplo": vagas_exemplo,
            "erros": erros[:5] if erros else [],
            "link_fonte": "https://github.com/backend-br/vagas/issues",
            "proxima_acao": "GET /vagas/buscar/Desenvolvedor"
        })
        
    except requests.exceptions.RequestException as e:
        return jsonify({
            "erro": f"Erro na requisição GitHub: {str(e)}",
            "url": url
        }), 500
    except Exception as e:
        return jsonify({
            "erro": f"Erro inesperado: {str(e)}"
        }), 500

# ============ DEBUG - VER ISSUES BRUTAS ============
@app.route('/debug/github-raw', methods=['GET'])
def debug_github():
    """
    Retorna as issues BRUTAS do GitHub para debug
    Mostra exatamente o que a API retorna
    """
    url = "https://api.github.com/repos/backend-br/vagas/issues"
    
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'Flask-Job-Scraper-BR/1.0'
    }
    
    params = {
        'state': 'open',
        'per_page': 10
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        issues = response.json()
        
        # Retorna só título e link das primeiras 10
        resumo = []
        for i, issue in enumerate(issues[:10], 1):
            resumo.append({
                "numero": i,
                "titulo": issue.get('title', 'N/A'),
                "link": issue.get('html_url', 'N/A'),
                "data": issue.get('created_at', 'N/A')[:10]
            })
        
        return jsonify({
            "total_issues": len(issues),
            "primeiras_10": resumo,
            "api_funciona": "✅ SIM"
        })
        
    except Exception as e:
        return jsonify({
            "erro": str(e),
            "api_funciona": "❌ NÃO"
        }), 500

if __name__ == '__main__':
    init_db()
    print("=" * 70)
    print("🚀 API VAGAS - BACKEND BRASIL")
    print("=" * 70)
    print("\n📊 Visualizar:")
    print("   GET /vagas                          → Todas")
    print("   GET /vagas/python                   → Python")
    print("   GET /vagas/buscar/Desenvolvedor     → Busca 'Desenvolvedor'")
    print("   GET /vagas/buscar/Junior            → Busca 'Junior'")
    print("\n🔥 Scraping:")
    print("   GET /scraping/backend-br            → Busca GitHub")
    print("\n🐛 Debug:")
    print("   GET /debug/github-raw               → Ver dados brutos")
    print("\n🌐 http://127.0.0.1:5000")
    print("=" * 70)
    app.run(debug=True)
