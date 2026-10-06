-- Normalização usada dos dois lados de todo cruzamento (CNPJ, CNEFE e as próximas fontes).
-- As funções guardam o search_path de quando foram criadas, então funcionam em qualquer sessão.
--
-- Duas chaves de logradouro:
--   logr_chave     curta: sem tipo, sem título, sem conectivo.   "R DR SAO JOSE" -> "JOSE"
--   logr_completa  sem tipo e sem conectivo, títulos por extenso.  "R DR SAO JOSE" -> "DOUTOR SAO JOSE"
-- A curta só é usada quando o CEP já confirma a rua; os níveis sem CEP usam a completa,
-- para "R. São José" e "R. José" não virarem a mesma rua.

CREATE OR REPLACE FUNCTION norm_txt(t TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path FROM CURRENT AS $$
    SELECT NULLIF(btrim(regexp_replace(
        upper(public.unaccent('public.unaccent'::regdictionary, coalesce(t, ''))),
        '[^A-Z0-9]+', ' ', 'g')), '')
$$;

-- tipos de logradouro: só removidos quando abrem o nome
CREATE OR REPLACE FUNCTION tipos_logradouro() RETURNS TEXT[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT ARRAY['R','RUA','AV','AVE','AVENIDA','AL','ALAMEDA','TV','TRV','TRAV','TRAVESSA',
                 'PC','PCA','PRC','PRACA','ROD','RODOVIA','EST','ESTR','ESTRADA','LG','LGO','LARGO',
                 'VD','VIADUTO','VIA','BC','BECO','LAD','LADEIRA','PQ','PRQ','PARQUE','SV','SERVIDAO',
                 'PSG','PASSAGEM','CJ','CONJ','CONJUNTO','LOT','LOTEAMENTO','ACESSO','MARGINAL','CONTORNO']
$$;

-- abreviação de título -> forma por extenso (mesma posição nos dois arrays)
CREATE OR REPLACE FUNCTION titulos_abrev() RETURNS TEXT[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT ARRAY['DR','DRA','PROF','PROFA','ENG','GAL','GEN','CEL','MAL','PE','STA','STO','S','CAP','TEN',
                 'DEP','SEN','VER','PRES','MAJ','DES','COM','COMEND','BRIG','ALM','MONS','SGT','CB','SD',
                 'VISC','BAR','CONS','MIN','GOV','PREF','MME','NSRA']
$$;

CREATE OR REPLACE FUNCTION titulos_extenso() RETURNS TEXT[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT ARRAY['DOUTOR','DOUTORA','PROFESSOR','PROFESSORA','ENGENHEIRO','GENERAL','GENERAL','CORONEL',
                 'MARECHAL','PADRE','SANTA','SANTO','SAO','CAPITAO','TENENTE','DEPUTADO','SENADOR','VEREADOR',
                 'PRESIDENTE','MAJOR','DESEMBARGADOR','COMENDADOR','COMENDADOR','BRIGADEIRO','ALMIRANTE',
                 'MONSENHOR','SARGENTO','CABO','SOLDADO','VISCONDE','BARAO','CONSELHEIRO','MINISTRO',
                 'GOVERNADOR','PREFEITO','MADRE','NOSSA SENHORA']
$$;

-- palavras que somem da chave curta além dos títulos acima
CREATE OR REPLACE FUNCTION titulos_outros() RETURNS TEXT[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT ARRAY['ENGENHEIRA','FREI','DOM','D','DONA','IR','IRMA','IRMAO','N','NS','NOSSA','SENHORA']
$$;

CREATE OR REPLACE FUNCTION conectivos() RETURNS TEXT[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT ARRAY['DE','DA','DO','DAS','DOS','E']
$$;

-- tokens do logradouro sem o tipo inicial (mantém ao menos um token)
CREATE OR REPLACE FUNCTION tokens_logradouro(t TEXT) RETURNS TEXT[]
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE SET search_path FROM CURRENT AS $$
DECLARE
    toks TEXT[];
    i INT := 1;
BEGIN
    toks := regexp_split_to_array(norm_txt(t), ' ');
    IF toks IS NULL OR array_length(toks, 1) IS NULL THEN
        RETURN NULL;
    END IF;
    WHILE i < array_length(toks, 1) AND toks[i] = ANY (tipos_logradouro()) LOOP
        i := i + 1;
    END LOOP;
    RETURN toks[i:];
END
$$;

CREATE OR REPLACE FUNCTION norm_logradouro(t TEXT) RETURNS TEXT
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE SET search_path FROM CURRENT AS $$
DECLARE
    toks TEXT[] := tokens_logradouro(t);
    fora TEXT[] := titulos_abrev() || titulos_extenso() || titulos_outros() || conectivos();
    saida TEXT[] := '{}';
    tk TEXT;
BEGIN
    IF toks IS NULL THEN
        RETURN NULL;
    END IF;
    FOREACH tk IN ARRAY toks LOOP
        IF NOT tk = ANY (fora) THEN
            saida := saida || tk;
        END IF;
    END LOOP;
    IF array_length(saida, 1) IS NULL THEN
        RETURN array_to_string(toks, ' ');
    END IF;
    RETURN array_to_string(saida, ' ');
END
$$;

CREATE OR REPLACE FUNCTION norm_logradouro_completa(t TEXT) RETURNS TEXT
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE SET search_path FROM CURRENT AS $$
DECLARE
    toks TEXT[] := tokens_logradouro(t);
    abrev TEXT[] := titulos_abrev();
    extenso TEXT[] := titulos_extenso();
    saida TEXT[] := '{}';
    tk TEXT;
    pos INT;
BEGIN
    IF toks IS NULL THEN
        RETURN NULL;
    END IF;
    FOREACH tk IN ARRAY toks LOOP
        CONTINUE WHEN tk = ANY (conectivos());
        pos := array_position(abrev, tk);
        saida := saida || CASE WHEN pos IS NULL THEN tk ELSE extenso[pos] END;
    END LOOP;
    IF array_length(saida, 1) IS NULL THEN
        RETURN array_to_string(toks, ' ');
    END IF;
    RETURN array_to_string(saida, ' ');
END
$$;

-- nome de empresa ou estabelecimento: sem sufixo societário, sem CPF e sem conectivo
CREATE OR REPLACE FUNCTION norm_nome(t TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path FROM CURRENT AS $$
    SELECT NULLIF(array_to_string(ARRAY(
        SELECT tk FROM unnest(regexp_split_to_array(norm_txt(regexp_replace(coalesce(t, ''), '[0-9.\-/]{11,}', ' ', 'g')), ' ')) AS tk
        WHERE tk <> '' AND NOT tk = ANY (ARRAY['LTDA','ME','EPP','EIRELI','SA','S','A','SS','CIA','MEI','EI',
                                               'SOCIEDADE','LIMITADA','EMPRESARIA','UNIPESSOAL'] || conectivos())
    ), ' '), '')
$$;

-- número predial: primeiro grupo de dígitos; "S/N", "SN", "0" e vazio viram NULL
CREATE OR REPLACE FUNCTION norm_numero(t TEXT) RETURNS INTEGER
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT NULLIF(left(substring(coalesce(t, '') FROM '[0-9]+'), 6)::INT, 0)
$$;

CREATE OR REPLACE FUNCTION norm_cep(t TEXT) RETURNS VARCHAR(8)
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN length(d) = 8 AND d <> '00000000' THEN d END
    FROM (SELECT regexp_replace(coalesce(t, ''), '[^0-9]', '', 'g') AS d) x
$$;

-- data da Receita (AAAAMMDD); vazia, zerada ou inválida vira NULL
CREATE OR REPLACE FUNCTION data_rfb(t TEXT) RETURNS DATE
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
BEGIN
    IF t IS NULL OR t !~ '^[0-9]{8}$' OR t = '00000000' THEN
        RETURN NULL;
    END IF;
    RETURN make_date(substr(t, 1, 4)::INT, substr(t, 5, 2)::INT, substr(t, 7, 2)::INT);
EXCEPTION WHEN others THEN
    RETURN NULL;
END
$$;

-- CPF que a Receita põe na razão social do MEI e do empresário individual (11 dígitos, com ou sem pontuação)
CREATE OR REPLACE FUNCTION cpf_no_texto(t TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT regexp_replace(m[1], '[^0-9]', '', 'g')
    FROM (SELECT regexp_match(coalesce(t, ''), '(?<![0-9])([0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2})(?![0-9])') AS m) x
    WHERE m IS NOT NULL
$$;

-- máscara no padrão do governo federal: ***.456.789-**
CREATE OR REPLACE FUNCTION mascarar_cpf(cpf TEXT) RETURNS VARCHAR(14)
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN cpf ~ '^[0-9]{11}$' THEN '***.' || substr(cpf, 4, 3) || '.' || substr(cpf, 7, 3) || '-**' END
$$;
