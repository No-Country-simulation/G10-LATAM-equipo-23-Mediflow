import json
from Agente import extrair
from roteamento import rotear
from pathlib import Path

texto = """HOSPITAL SANTA LUCIA - LAUDO DE EXAME RADIOLOGICO. Paciente: Carlos Eduardo Mendes, 52 anos.
Solicitante: Dra. Renata Silveira CRM-SP 145892. Exame: Tomografia de Torax com contraste.
Indicacao: Suspeita de embolia pulmonar aguda, dispneia subita. Achados: Falha de enchimento em
arteria pulmonar principal direita compativel com TEP agudo. CONCLUSAO: Quadro compativel com
Tromboembolismo Pulmonar Agudo. Sugere-se correlacao clinica urgente."""

doc = extrair(texto)
decisao = rotear(doc)

resultado = {
    "dados_extraidos": doc.model_dump(),
    "decisao_roteamento": decisao,
}
print(json.dumps(resultado, indent=2, ensure_ascii=False)) 

Path("saida").mkdir(exist_ok=True)
Path("saida/resultado.json").write_text(
    json.dumps(resultado, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
