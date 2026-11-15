
const areas = [					
	{"codigo": "1", "descricao": "Cível"},
	{"codigo": "2", "descricao": "Criminal"}
];

const tipos = [					
	{"areaId": "3", "servTipoId": "151", "codigo": "6", "descricao": "Turma Recursal Cível e Criminal"},
	{"areaId": "3", "servTipoId": "151", "codigo": "66", "descricao": "UPJ Turma Recursal"},
	{"areaId": "1", "servTipoId": "15", "codigo": "14", "descricao": "Câmaras Cíveis"},
	{"areaId": "2", "servTipoId": "15", "codigo": "20", "descricao": "Câmaras Criminais"},
	{"areaId": "1", "servTipoId": "15", "codigo": "21", "descricao": "Seções Cíveis"},
	{"areaId": "2", "servTipoId": "15", "codigo": "46", "descricao": "Seção Criminal"},
	{"areaId": "1", "servTipoId": "15", "codigo": "22", "descricao": "Órgão Especial"},
	{"areaId": "2", "servTipoId": "15", "codigo": "22", "descricao": "Órgão Especial"},
	{"areaId": "1", "servTipoId": "15", "codigo": "41", "descricao": "Conselho Superior de Magistratura"},
	{"areaId": "1", "servTipoId": "15", "codigo": "10", "descricao": "Plantão 2º Grau - Órgão Especial"},
	{"areaId": "2", "servTipoId": "15", "codigo": "10", "descricao": "Plantão 2º Grau - Órgão Especial"},
	{"areaId": "1", "servTipoId": "15", "codigo": "70", "descricao": "Plantão 2º Grau - Câmaras Cíveis"},
	{"areaId": "2", "servTipoId": "15", "codigo": "71", "descricao": "Plantão 2º Grau - Câmaras Criminais"},
	{"areaId": "1", "servTipoId": "16", "codigo": "1", "descricao": "Juizado Especial Cível"},			
	{"areaId": "2", "servTipoId": "16", "codigo": "2", "descricao": "Juizado Especial Criminal"},			
	{"areaId": "1", "servTipoId": "16", "codigo": "3", "descricao": "Juizado Especial Cível e Criminal"},
	{"areaId": "2", "servTipoId": "16", "codigo": "3", "descricao": "Juizado Especial Cível e Criminal"},			
	{"areaId": "1", "servTipoId": "16", "codigo": "26", "descricao": "Juizado Especial Fazenda Pública"},
	{"areaId": "2", "servTipoId": "16", "codigo": "39", "descricao": "Juizado de Violência Doméstica"},
	{"areaId": "1", "servTipoId": "16", "codigo": "27", "descricao": "Varas Cíveis"},
	{"areaId": "2", "servTipoId": "16", "codigo": "47", "descricao": "Varas Criminais"},			
	{"areaId": "1", "servTipoId": "16", "codigo": "9", "descricao": "Família"},
	{"areaId": "1", "servTipoId": "16", "codigo": "43", "descricao": "Infância e Juventude Cível"},			
	{"areaId": "2", "servTipoId": "16", "codigo": "44", "descricao": "Infância e Juventude Infracional"},
	{"areaId": "2", "servTipoId": "16", "codigo": "11", "descricao": "Execução Penal"},
	{"areaId": "2", "servTipoId": "16", "codigo": "63", "descricao": "Execução de Pena Alternativa"},
	{"areaId": "1", "servTipoId": "16", "codigo": "45", "descricao": "Auditoria Militar Cível"},
	{"areaId": "2", "servTipoId": "16", "codigo": "60", "descricao": "Auditoria Militar Criminal"},
	{"areaId": "1", "servTipoId": "16", "codigo": "34", "descricao": "Fazenda Pública Estadual"},
	{"areaId": "1", "servTipoId": "16", "codigo": "8", "descricao": "Fazenda Pública Estadual - Execução Fiscal"},
	{"areaId": "1", "servTipoId": "16", "codigo": "35", "descricao": "Fazenda Pública Estadual Interior"},
	{"areaId": "1", "servTipoId": "16", "codigo": "36", "descricao": "Fazenda Pública Municipal"},
	{"areaId": "1", "servTipoId": "16", "codigo": "7", "descricao": "Fazenda Pública Municipal - Execução Fiscal"},
	{"areaId": "1", "servTipoId": "16", "codigo": "37", "descricao": "Fazenda Pública Municipal Interior"},
	{"areaId": "1", "servTipoId": "16", "codigo": "12", "descricao": "Fazenda Pública Mista"},			
	{"areaId": "1", "servTipoId": "16", "codigo": "69", "descricao": "Fazenda Pública Mista - Execução Fiscal"},
	{"areaId": "1", "servTipoId": "16", "codigo": "42", "descricao": "Plantão 1º Grau"},
	{"areaId": "2", "servTipoId": "16", "codigo": "42", "descricao": "Plantão 1º Grau"},			
	{"areaId": "1", "servTipoId": "16", "codigo": "72", "descricao": "UPJ Cível"},
	{"areaId": "2", "servTipoId": "16", "codigo": "61", "descricao": "UPJ Criminal"},
	{"areaId": "1", "servTipoId": "16", "codigo": "49", "descricao": "UPJ Sucessões"},
	{"areaId": "1", "servTipoId": "16", "codigo": "58", "descricao": "UPJ Família"},
	{"areaId": "2", "servTipoId": "16", "codigo": "67", "descricao": "UPJ de Violência Doméstica"},
	{"areaId": "1", "servTipoId": "16", "codigo": "68", "descricao": "UPJ Família Interior"},
	{"areaId": "1", "servTipoId": "16", "codigo": "81", "descricao": "UPJ Fazenda Pública Estadual"},
	{"areaId": "1", "servTipoId": "16", "codigo": "82", "descricao": "UPJ Fazenda Pública Municipal"},
	{"areaId": "1", "servTipoId": "16", "codigo": "83", "descricao": "UPJ dos Juizados Especiais Cíveis"},
	{"areaId": "1", "servTipoId": "16", "codigo": "64", "descricao": "UPJ Juizado Especial da Fazenda Pública"}			
];

function IrParaOnClick(){
	submitForm($('#CaixaTextoPosicionar').val()-1);
}
function abrirArquivo(action, id){
	var token = $('#g-recaptcha-response').val();
	$('<form action="'+ encodeURI(action + '?PaginaAtual=1&Id_Arquivo=' + id + '&g-recaptcha-response=' + token) +'" method="post"></form>').appendTo('body').submit().remove();
}		
function inicializarAreas(){
	$("#Id_Area").find("option[value != '0']").remove();
	var areaFiltrada = ($("#Id_Instancia").val() == "151") ? areas.filter(e => e.codigo == "0") : areas;			
	areaFiltrada.forEach((e) => $('#Id_Area').append('<option value="' + e.codigo + '">' + e.descricao + '</option>'));			
}		
function atualizarAreas (servTipoId){
	$("#Id_Area").find("option[value != '0']").remove(); // limpa todas as opções diferente de TODOS
	if (servTipoId != "151"){
		areas.forEach((e) => $('#Id_Area').append('<option value="' + e.codigo + '">' + e.descricao + '</option>'));				
	}
}			
function filtrarOpcoes (areaId, servTipoId){
	var tiposFiltrados = [];
	if (servTipoId == "0" && areaId =="0"){
		tiposFiltrados = tipos;
	} else {
		if (servTipoId != "0"){ // se escolheu uma opção válida
			tiposFiltrados = tipos.filter(e => e.servTipoId == servTipoId);
		} 
		if (areaId != "0"){
			if (servTipoId != "0"){
				tiposFiltrados = tiposFiltrados.filter(e => e.areaId == areaId);
			} else {
				tiposFiltrados = tipos.filter(e => e.areaId == areaId);
			}				
		}
	}
	// Filtra o array para tirar os elementos repetidos
	const tiposDistintos = [...new Map(tiposFiltrados.map(item => [item['codigo'], item])).values()];			
	$("#Id_ServentiaSubTipo").find("option[value != '0']").remove();
	tiposDistintos.forEach((e) => $('#Id_ServentiaSubTipo').append('<option value="' + e.codigo + '">' + e.descricao + '</option>'));			
}

function notNullNotVazio(texto) {
	return texto && texto.toLowerCase() != 'null' && texto.toLowerCase() != 'undefined';
}

function copiarNumeroProcessoAreaTransferencia(numeroProcesso, formatar) {
	const textoOriginal = numeroProcesso;
	const textoFinal = formatar ? textoOriginal : textoOriginal.replace(/\D/g, '');

	navigator.clipboard.writeText(textoFinal);
	alert('Número de processo copiado para a área de transferência');
}


function copiarConteudoTexto(nodePai) {
	var elementoTexto = $(nodePai).find('.conteudoTexto');
	if (elementoTexto) {
		var range = document.createRange();
		range.selectNodeContents(elementoTexto[0]);
		window.getSelection().addRange(range);
		var realizador = formatarRealizador(nodePai.dataset.realizador);
		var classeProcesso = nodePai.dataset.classeAcao;
		var numeroProcesso = nodePai.dataset.numero;
		var classeNumeroProcesso = formatarClasseProcessoNumeroRodape(classeProcesso, numeroProcesso);
		var serventia = nodePai.dataset.serventia;
		var dataMovi = formatarDataJulgado(nodePai.dataset.moviData);
		var footer = '\n\n(TJGO, ';
		if (classeNumeroProcesso) {
			footer += classeNumeroProcesso + ', ';
		}
		if (notNullNotVazio(realizador)) {
			footer += realizador + ', ';
		}
		if (notNullNotVazio(serventia)) {
			footer += serventia + ', ';
		}
		if (notNullNotVazio(dataMovi)) {
			footer += dataMovi + ', ';
		}
		footer = footer.substring(0, footer.length - 2);
		footer += ')';

		navigator.clipboard.writeText(elementoTexto.text() + footer);
	}
}

function formatarClasseProcessoNumeroRodape(classeProcesso, numeroProcesso) {
	var textoFormatado = '';
	if (notNullNotVazio(classeProcesso)) {
		var classeFrags = classeProcesso.split(/\s*->\s*/);

		while (classeFrags.length > 0) {
			var fragmento = classeFrags.pop();
			if (notNullNotVazio(fragmento)) {
				textoFormatado = fragmento;
				break;
			}
		}
	}

	if (notNullNotVazio(numeroProcesso)) {
		if (textoFormatado) {
			textoFormatado += ' ';
		}
		textoFormatado += 'nº ' + numeroProcesso;
	}
	return textoFormatado;
}

function formatarRealizador(realizador) {
	if (!notNullNotVazio(realizador)) {
		return '';
	}
	if (/desembargadora?/i.test(realizador)) {
		return 'Rel. ' + realizador.replaceAll(/[\s-(]*desembargadora?[\s-)]*/gi, '');
	}
	if (/juiz [^)]*/i.test(realizador)) {
		return realizador.replaceAll(/[\s-(]*juiz [^)]*[\s-)]*/gi, '');
	}
	if (/magistrad[oa] [^)]*/i.test(realizador)) {
		return realizador.replaceAll(/[\s-(]*magistrad[oa] [^)]*[\s-)]*/gi, '');
	}
	return realizador;
}

function formatarDataJulgado(dataHora, capitalizar) {
	if (!notNullNotVazio(dataHora)) {
		return '';
	}
	var julgado = 'julgado';
	if (capitalizar) {
		julgado = 'Julgado';
	}
	return julgado +' em ' + dataHora.replace(/\s*\d\d:\d\d:\d\d/, '');
}

/**
 * Aplica na ementa as marcações de destaque devolvidas pelo elasticsearch.
 * Cada destaque já vem com as tags <em>: localiza-se o trecho sem as tags
 * dentro da ementa e substitui-se pelo trecho destacado.
 */
function destacarEmenta(ementa, destaques) {
	if (!ementa) {
		return '';
	}
	if (!destaques || destaques.length == 0) {
		return ementa;
	}
	var texto = ementa;
	for (var i = 0; i < destaques.length; i++) {
		var termoDestaque = destaques[i];
		var termoSemDestaque = termoDestaque.replace(/<em[^>]*>|<\/em>/g, '');
		var offset = texto.indexOf(termoSemDestaque);
		if (offset < 0) {
			continue;
		}
		texto = texto.substring(0, offset) + termoDestaque + texto.substring(offset + termoSemDestaque.length);
	}
	return texto;
}

/**
 * Lê os destaques renderizados pelo jsp e descarta os elementos auxiliares que os
 * carregavam. O resultado fica guardado no próprio item, pois os destaques ainda
 * são necessários quando o texto formatado chega pelo ajax, depois da remoção.
 */
function lerDestaquesEmenta(nodePai) {
	var destaquesGuardados = $(nodePai).data('ementaDestaques');
	if (destaquesGuardados) {
		return destaquesGuardados;
	}
	var destaques = $(nodePai).find('.ementaDestaque').map(function() {
		return $(this).text().trim();
	}).get();
	$(nodePai).data('ementaDestaques', destaques);
	$(nodePai).find('.ementaDestaques').remove();
	return destaques;
}

/**
 * Extrai dos destaques os termos marcados com <em>, sem repetição e preservando os
 * atributos da tag, para que possam ser reaplicados no texto formatado.
 */
function extrairTermosDestaque(destaques) {
	var termos = [];
	var termosLidos = {};
	var regexEm = /<em([^>]*)>([\s\S]*?)<\/em>/gi;
	for (var i = 0; i < destaques.length; i++) {
		var marcacao;
		while ((marcacao = regexEm.exec(destaques[i])) !== null) {
			var texto = marcacao[2].trim();
			var chave = texto.toLowerCase();
			if (!notNullNotVazio(texto) || termosLidos[chave]) {
				continue;
			}
			termosLidos[chave] = marcacao[1];
			termos.push(texto);
		}
	}
	// termos maiores primeiro, para que um termo curto não quebre o casamento de um mais longo
	termos.sort(function(termoA, termoB) {
		return termoB.length - termoA.length;
	});
	return {
		'termos': termos,
		'atributos': termosLidos
	};
}

function escaparRegex(texto) {
	return texto.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function escaparHtml(texto) {
	return $('<div></div>').text(texto).html();
}

/**
 * Devolve o html do texto com os termos destacados, ou null caso nenhum termo
 * ocorra nele. Só são destacadas palavras inteiras.
 */
function destacarTermos(texto, termosDestaque) {
	if (!notNullNotVazio(texto) || termosDestaque.termos.length == 0) {
		return null;
	}
	var alternativas = termosDestaque.termos.map(escaparRegex).join('|');
	var letra = '0-9A-Za-zÀ-ÿ_';
	var regex = new RegExp('(^|[^' + letra + '])(' + alternativas + ')(?![' + letra + '])', 'gi');
	var html = '';
	var posicao = 0;
	var ocorrencia;
	while ((ocorrencia = regex.exec(texto)) !== null) {
		var termo = ocorrencia[2];
		var inicio = ocorrencia.index + ocorrencia[1].length;
		var atributos = termosDestaque.atributos[termo.toLowerCase()];
		html += escaparHtml(texto.substring(posicao, inicio));
		html += '<em' + atributos + '>' + escaparHtml(termo) + '</em>';
		posicao = inicio + termo.length;
	}
	if (posicao == 0) {
		return null;
	}
	return html + escaparHtml(texto.substring(posicao));
}

/**
 * Aplica os destaques no texto formatado, cujo conteúdo está subdividido em
 * parágrafos. Cada parágrafo já visitado é marcado, pois o texto formatado chega
 * pelo ajax e este método pode ser executado mais de uma vez sobre o mesmo item.
 */
function aplicarDestaquesTextoFormatado(nodePai, destaques) {
	var paragrafos = $(nodePai).find('.conteudoFormatado p:not([data-destaque-aplicado])');
	if (paragrafos.length == 0) {
		return;
	}
	var termosDestaque = extrairTermosDestaque(destaques);
	paragrafos.each(function() {
		var html = destacarTermos($(this).text(), termosDestaque);
		if (html !== null) {
			$(this).html(html);
		}
		$(this).attr('data-destaque-aplicado', 'true');
	});
}

/**
 * Lê a ementa e os destaques renderizados pelo jsp e aplica os destaques tanto no
 * texto corrido da ementa quanto nos parágrafos do texto formatado.
 */
function aplicarDestaquesEmenta(nodePai) {
	var destaques = lerDestaquesEmenta(nodePai);
	if (destaques.length == 0) {
		return;
	}
	var elementoEmenta = $(nodePai).find('.ementa:not([data-destaque-aplicado])');
	if (elementoEmenta.length > 0) {
		elementoEmenta.html(destacarEmenta(elementoEmenta.text().trim(), destaques));
		elementoEmenta.attr('data-destaque-aplicado', 'true');
	}
	aplicarDestaquesTextoFormatado(nodePai, destaques);
}

function atualizarDadosJurisprudencia() {
	var realizador = formatarRealizador(this.dataset.realizador);
	$(this).find('.jurisprudencia_realizador').text(realizador);
	var dataMovi = formatarDataJulgado(this.dataset.moviData, true);
	$(this).find('.jurisprudencia_data').text(dataMovi);
	aplicarDestaquesEmenta(this);
}

function appendStringsParagrafos(container, stringArray) {
	const paragraphs = stringArray.map(text => {
		const p = document.createElement('p');
		p.textContent = text;
		return p;
	});
	container.append(...paragraphs);
}

function atualizarTextoFormatado(nodePaiArray, item) {
	for (const nodePai of nodePaiArray.toArray()) {
		if (nodePai.dataset.idArquivo !== item.idArquivo) {
			continue;
		}
		const container = $(nodePai).find('.conteudoFormatado');
		const containerSemFormatacao = $(nodePai).find('.ementa');
		const textoSemFormatacao = containerSemFormatacao.text();
		let paragrafos = item.paragrafos;
		try {
			paragrafos = ParagraphBreaks.applyBreaks(textoSemFormatacao, paragrafos);
		} catch(e) {
			console.error(e);
		}
		appendStringsParagrafos(container, paragrafos);
		aplicarDestaquesEmenta(nodePai);
		container.fadeIn();
		containerSemFormatacao.fadeOut();
	}
}

function aguardarBotaoBuscarAtivo() {
	const btnBuscarElement = document.querySelector('#btnBuscar');
	if (!btnBuscarElement || !btnBuscarElement.disabled) {
		return Promise.resolve();
	}
	return new Promise((resolve, reject) => {
		const observer = new MutationObserver((mutationList) => {
			const attrMutation = mutationList.filter((mut) => mut.type === 'attributes' && mut.attributeName ==="disabled");
			if (attrMutation.length !== 1) {
				reject('erro de observer em <aguardarBotaoBuscarAtivo>, num elementos: ' + attrMutation.length);
				return;
			}
			if (attrMutation[0].target !== btnBuscarElement) {
				reject('erro de observer em <aguardarBotaoBuscarAtivo>');
				return;
			}
			observer.disconnect();
			resolve();
		});
		observer.observe(btnBuscarElement, { attributes: true });
	});
}

async function desativarBotaoBuscar() {
	const btnBuscarElement = document.querySelector('#btnBuscar');
	if (!btnBuscarElement) {
		return;
	}
	await aguardarBotaoBuscarAtivo();
	btnBuscarElement.disabled = true;
}

function getCaptchaToken(recapchaAtivo) {
	if (!recapchaAtivo) {
		return Promise.resolve('');
	}

	return new Promise((resolve) => {
		var token = null;
		const cloudflareTokenField = $('#g-recaptcha-response').get(0);
		if (cloudflareTokenField.value) {
			token = cloudflareTokenField.value;
			// nao limpar valor do campo porque pode have chamada a mudanca de pagina ja ocorrendo
			resolve(token);
		}
		const observer = new MutationObserver(async (mutationList) => {
			const attrMutation = mutationList.filter((mut) => mut.type === 'attributes' && mut.attributeName ==="value");
			if (attrMutation.length !== 1) {
				return;
			}
			const field = attrMutation[0].target;
			if (!field.value) {
				return;
			}
			observer.disconnect();
			try {
				// na versao atual do script reCloudFlare.jspf, o botao eh desativado apos valor ser setado no input
				// aguardar esta desativacao para garantir que ele termine desativado ao fim do processo
				await desativarBotaoBuscar();
			} catch (msgErro) {
				console.error(msgErro);
				return;
			}
			token = field.value;
			field.value = "";
			resolve(token);
		});
		observer.observe(cloudflareTokenField, { attributes: true });
	});
}

function novoTokenCaptcha() {
	turnstile.reset("#widget-container");
}

async function consultaTextoFormatado(recapchaAtivo) {
	const divItens = $(".search-result");
	const dadosConsulta = divItens.toArray().map(item => item.dataset.idArquivo);
	if (dadosConsulta.length < 1) {
		return;
	}

	const token = await getCaptchaToken(recapchaAtivo);
	if (window.formSubmitInProgress) {
		// Usuario clicou em um dos links para mudar de pagina
		// Abortar formatacao de texto e deixar troca de pagina seguir
		return;
	}

	const data = {
		'arquivos': JSON.stringify(dadosConsulta),
		'g-recaptcha-response': token
	};
	try {
		const retorno = await $.ajax({
			type: "POST",
			url: 'ConsultaJurisprudencia?AJAX=ajax&PaginaAtual=6',
			context: document.body,
			data: data,
			timeout: 300000
		});
		if (!Array.isArray(retorno) || retorno.length === 0) {
			console.error(retorno);
			return;
		}
		retorno.forEach((item) =>{
			if (item.erro) {
				console.error(item);
				return;
			}
			atualizarTextoFormatado(divItens, item);
		});
	} catch (jqXHR) {
		console.error({'status': jqXHR.status, 'error': jqXHR.statusText});
	} finally {
		if (recapchaAtivo) {
			novoTokenCaptcha();
		}
	}
}

function setSelectOption(selectElement, value) {
	if (value) {
		var options = selectElement.options;
		for (var i = 0, optionsLength = options.length; i < optionsLength; i++) {
			if (options[i].value == value) {
				selectElement.selectedIndex = i;
				return true;
			}
		}
	}
	return false;
}
