import os
import sys

from loja import create_app
from loja.config import build_config
from loja.migrations import migrate

def main():
    # Carregar configurações base para saber onde está o banco
    cfg = build_config()
    db_path = cfg["DATABASE"]
    backup_dir = cfg["BACKUP_DIR"]

    # Migrar dados antigos ou criar schema novo
    print("Inicializando/atualizando banco de dados...")
    versao = migrate(db_path, backup_dir)
    print(f"Banco de dados na versão {versao}.")

    # Criar a aplicação Flask
    app = create_app()
    
    port = int(os.environ.get('PORT', 8000))
    is_dev = '--dev' in sys.argv or os.environ.get('FLASK_DEBUG') == '1'

    if is_dev:
        print(f"Iniciando em modo DEV na porta {port} (0.0.0.0)")
        app.run(debug=True, port=port, host="0.0.0.0")
    else:
        print(f"Iniciando Waitress na porta {port}")
        from waitress import serve
        serve(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()