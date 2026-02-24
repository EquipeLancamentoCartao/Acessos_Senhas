import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import text
import io
# urllib.parse não é mais necessário se usarmos a conexão automática

# TESTE DE DIAGNÓSTICO
if st.checkbox("Debug: Verificar Credenciais"):
    st.write(f"Usuário no Secret: {st.secrets['connections']['tidb']['username']}")
    st.write(f"Senha tem {len(st.secrets['connections']['tidb']['password'])} caracteres")
    # Isso vai nos dizer se ele está lendo o arquivo certo

st.set_page_config(page_title="Gestor Pro TiDB", layout="wide")

# --- CONEXÃO AUTOMÁTICA ---
# O Streamlit lê o [connections.tidb] do seu Secrets automaticamente
try:
    conn = st.connection("tidb", type="sql")
except Exception as e:
    st.error(f"Erro ao conectar ao banco: {e}")
    st.stop()

# --- SENHA MESTRE ---
# Busca do bloco [admin] que você configurou
SENHA_MESTRE = st.secrets["admin"]["SENHA_MESTRE"]

# --- USUÁRIO ---
try:
    usuario_atual = st.user.get("email", "Admin_Local")
except:
    usuario_atual = "Admin_Local"

# --- FUNÇÕES ---
def load_data():
    # Carrega e garante que as colunas do DataFrame sejam sempre minúsculas
    df = conn.query("SELECT * FROM acessos", ttl=0)
    # df.columns = [c.lower() for c in df.columns]
    return df

def registrar_log(evento, detalhes):
    with conn.session as session:
        session.execute(
            text("INSERT INTO logs_alteracao (evento, usuario_executor, detalhes) VALUES (:ev, :us, :det)"),
            {"ev": evento, "us": usuario_atual, "det": detalhes}
        )
        session.commit()

def save_upload(df_upload, user):
    # Padroniza nomes das colunas da planilha para minúsculo para evitar erro de chave
    # df_upload.columns = [c.lower() for c in df_upload.columns]
    
    with conn.session as session:
        session.execute(text("TRUNCATE TABLE acessos;"))
        agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for _, row in df_upload.iterrows():
            query = text("""
                INSERT INTO acessos (Portal, Convenio, Consignataria, Acesso, Link, Senha, 
                                   `Alterado por`, `Horario da Alt.`, `Dono do Acesso`)
                VALUES (:p, :c, :con, :ace, :link, :sen, :alt, :hor, :dono)
            """)
            session.execute(query, {
                "p": row.get('Portal'), "c": row.get('Convenio'), "con": row.get('Consignataria'),
                "ace": row.get('Acesso'), "link": row.get('Link'), "sen": row.get('Senha'), 
                "alt": user, "hor": agora, "dono": row.get('Dono do Acesso')
            })
        session.commit()
    registrar_log("Upload Geral", f"Planilha com {len(df_upload)} linhas.")
    st.cache_data.clear()

def salvar_edicoes_diretas(df_editado, df_original):
    with conn.session as session:
        agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for i, row in df_editado.iterrows():
            if not row.equals(df_original.iloc[i]):
                # SEGURANÇA: Se a senha for asteriscos, não atualizamos o campo senha no banco!
                if row['Senha'] == "********":
                    query = text("""
                        UPDATE acessos SET 
                        Portal=:p, Convenio=:c, Consignataria=:con, Link=:link, Acesso=:ace, 
                        `Alterado por`=:alt, `Horario da Alt.`=:hor, `Dono do Acesso`=:dono
                        WHERE id=:id
                    """)
                    params = {
                        "p": row['Portal'], "c": row['Convenio'], "con": row['Consignataria'],
                        "link": row['Link'], "ace": row['Acesso'], "alt": usuario_atual, 
                        "hor": agora, "dono": row['Dono do Acesso'], "id": row['id']
                    }
                else:
                    query = text("""
                        UPDATE acessos SET 
                        Portal=:p, Convenio=:c, Consignataria=:con, Link=:link, Acesso=:ace, 
                        Senha=:sen, `Alterado por`=:alt, `Horario da Alt.`=:hor, `Dono do Acesso`=:dono
                        WHERE id=:id
                    """)
                    params = {
                        "p": row['Portal'], "c": row['Convenio'], "con": row['Consignataria'],
                        "link": row['Link'], "ace": row['Acesso'], "sen": row['Senha'], 
                        "alt": usuario_atual, "hor": agora, "dono": row['Dono do Acesso'], "id": row['id']
                    }
                session.execute(query, params)
        session.commit()
    registrar_log("Edição Direta", "Alteração manual via tabela.")
    st.cache_data.clear()
    st.rerun()

# --- SIDEBAR ---
st.sidebar.header("🔐 Controle")
senha_view = st.sidebar.text_input("Senha Master", type="password")
SENHA_MESTRE = "282723"
mostrar_senhas = st.sidebar.toggle("👁️ Revelar Senhas", value=False)

uploaded_file = st.sidebar.file_uploader("Substituir base", type=['csv', 'xlsx'])
if uploaded_file and st.sidebar.button("⚠️ Sobrescrever Banco"):
    df_new = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
    save_upload(df_new, usuario_atual)
    st.sidebar.success("Atualizado!")

st.sidebar.divider()

# 3. Filtros Dinâmicos
st.sidebar.subheader("Filtros")
df_raw = load_data()

# Criando dicionário para armazenar filtros
filtros = {}
for col in ['Portal', 'Convenio', 'Consignataria', 'Dono do Acesso']:
    filtros[col] = st.sidebar.multiselect(f"Filtrar {col.title()}", options=df_raw[col].unique())

if st.sidebar.button("Limpar Filtros"):
    st.rerun()

# --- CORPO PRINCIPAL ---
if senha_view == SENHA_MESTRE:
    st.title("🔑 Painel de Credenciais")
    df_raw = load_data()

    # Aplicando Filtros no DataFrame
    df_filtrado = df_raw.copy()
    for col, values in filtros.items():
        if values:
            df_filtrado = df_filtrado[df_filtrado[col].isin(values)]

    # Configuração da Tabela (Link Clicável)    
    config_colunas = {
        "id": None,
        "Link": st.column_config.LinkColumn("Link de Acesso"),
        "Horario da Alt.": st.column_config.DatetimeColumn("Última Alteração", disabled=True),
        "Alterado por": st.column_config.TextColumn("Quem Alterou", disabled=True)
    }

    df_exibicao = df_filtrado.copy()
    if not mostrar_senhas:
        df_exibicao['Senha'] = "********"
        config_colunas["Senha"] = st.column_config.TextColumn("Senha (Protegida)", disabled=True)
    else:
        config_colunas["Senha"] = st.column_config.TextColumn("Senha (Editável)")
        
    

    df_editado = st.data_editor(
        df_exibicao,
        column_config=config_colunas,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic"
    )
    # 1. Criar um buffer na memória
    buffer = io.BytesIO()

    # 2. Salvar o Excel dentro desse buffer
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_raw.to_excel(writer, index=False, sheet_name='Acessos')

    # 3. Preparar o botão de download com os dados do buffer
    st.download_button(
        label="📥 Baixar Backup XLSX",
        data=buffer.getvalue(),
        file_name='backup_acessos.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    # --- PARTE FINAL DO CÓDIGO ---
    if st.button("💾 Salvar Alterações", type="primary"):
        # Chamamos a função passando o que está na tela (editado) 
        # e o que veio do banco (original) para comparação
        salvar_edicoes_diretas(df_editado, df_raw)
        st.success("Alterações salvas com sucesso!")

    st.divider()
    with st.expander("📜 Histórico de Alterações (Logs)"):
        # 1. Busca os logs diretamente do banco
        df_logs = conn.query("SELECT * FROM logs_alteracao ORDER BY data_hora DESC", ttl=0)
    
    if not df_logs.empty:
        # 2. Exibe a tabela de logs (apenas leitura)
        st.dataframe(
            df_logs, 
            use_container_width=True,
            column_config={
                "id": None, # Esconde o ID do log
                "data_hora": st.column_config.DatetimeColumn("Data/Hora"),
                "usuario_executor": "Usuário",
                "evento": "Ação",
                "detalhes": "Detalhes da Alteração"
            }
        )
        
        # 3. Botão para baixar os logs em Excel
        buffer_logs = io.BytesIO()
        with pd.ExcelWriter(buffer_logs, engine='xlsxwriter') as writer:
            df_logs.to_excel(writer, index=False, sheet_name='Logs')
            
        st.download_button(
            label="📥 Baixar Histórico Completo (XLSX)",
            data=buffer_logs.getvalue(),
            file_name=f'logs_sistema_{datetime.now().strftime("%d-%m-%Y")}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    else:
        st.info("Ainda não há registros no histórico.")

else:
    st.warning("Insira a senha master.")