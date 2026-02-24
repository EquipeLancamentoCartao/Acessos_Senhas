import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Gestor Pro TiDB", layout="wide")

# --- CONEXÃO ---
conn = st.connection("tidb", type="sql")
usuario_atual = st.user.email if st.user.email else "Admin_Local"

# --- FUNÇÕES DE PERSISTÊNCIA ---
def load_data():
    # Buscamos sempre do banco. O cache é limpo manualmente no upload/edição.
    return conn.query("SELECT * FROM acessos", ttl=0)

def registrar_log(evento, detalhes):
    with conn.session as session:
        session.execute(
            "INSERT INTO logs_alteracao (evento, usuario_executor, detalhes) VALUES (:ev, :us, :det)",
            {"ev": evento, "us": usuario_atual, "det": detalhes}
        )
        session.commit()

def salvar_edicoes_diretas(df_editado, df_original):
    # Identifica o que mudou comparando o dataframe editado com o original
    # Para simplificar, vamos atualizar os registros que foram alterados
    with conn.session as session:
        agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for i, row in df_editado.iterrows():
            # Verifica se a linha atual é diferente da original
            if not row.equals(df_original.iloc[i]):
                query = """
                    UPDATE acessos SET 
                    portal=:p, convenio=:c, consignataria=:con, acesso=:ace, 
                    senha=:sen, alterado_por=:alt, horario_alt=:hor, dono_acesso=:dono
                    WHERE id=:id
                """
                session.execute(query, {
                    "p": row['portal'], "c": row['convenio'], "con": row['consignataria'],
                    "ace": row['acesso'], "sen": row['senha'], "alt": usuario_atual, 
                    "hor": agora, "dono": row['dono_acesso'], "id": row['id']
                })
        session.commit()
    registrar_log("Edição Direta", "Alteração manual de células na tabela")
    st.cache_data.clear()
    st.rerun()

# --- SIDEBAR ---
st.sidebar.header("🔐 Controle de Acesso")
senha_view = st.sidebar.text_input("Senha Master", type="password")
SENHA_MESTRE = "282723" # Use st.secrets em produção

mostrar_senhas = st.sidebar.toggle("👁️ Revelar Senhas", value=False)


st.sidebar.divider()
st.sidebar.subheader("Upload de Planilha")
uploaded_file = st.sidebar.file_uploader("Substituir base de dados", type=['csv', 'xlsx'])

if uploaded_file and st.sidebar.button("⚠️ Sobrescrever Banco"):
    df_new = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
    # Lógica de salvar (Truncate + Insert) como vimos antes...
    # [Inserir aqui a função save_upload anterior]
    registrar_log("Upload Geral", f"Substituição total: {len(df_new)} linhas")
    st.cache_data.clear()
    st.rerun()

# --- CORPO PRINCIPAL ---
if senha_view == SENHA_MESTRE:
    st.title("🔑 Painel de Credenciais")
    
    df_raw = load_data()
    
    # Configuração das Colunas
    config_colunas = {
        "id": None, # Esconde o ID
        "acesso": st.column_config.LinkColumn("Link de Acesso"),
        "horario_alt": st.column_config.DatetimeColumn("Última Alteração", disabled=True),
        "alterado_por": st.column_config.TextColumn("Quem Alterou", disabled=True)
    }

    # Lógica de Máscara de Senha
    df_exibicao = df_raw.copy()
    if not mostrar_senhas:
        df_exibicao['senha'] = "********"
        # Se as senhas estão ocultas, desabilitamos a edição da coluna de senha para evitar erros
        config_colunas["senha"] = st.column_config.TextColumn("Senha (Protegida)", disabled=True)
    else:
        config_colunas["senha"] = st.column_config.TextColumn("Senha (Editável)")

    # TABELA EDITÁVEL
    st.write("Dica: Você pode editar as células diretamente abaixo e clicar em salvar.")
    df_editado = st.data_editor(
        df_exibicao,
        column_config=config_colunas,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic" # Permite adicionar/remover linhas
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("💾 Salvar Alterações", type="primary"):
            salvar_edicoes_diretas(df_editado, df_raw)
    with col2:
        # Download
        csv = df_raw.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Backup CSV", data=csv, file_name='backup_acessos.csv')

else:
    st.warning("Aguardando autenticação na barra lateral...")