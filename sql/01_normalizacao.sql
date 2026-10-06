-- Normalização de endereço usada dos dois lados do cruzamento (CNPJ e CNEFE).
-- Mesma função nos dois lados: abreviação e título somem igual, então "R DR FAIVRE" e
-- "RUA DOUTOR FAIVRE" viram a mesma chave.

CREATE OR REPLACE FUNCTION cwb.norm_txt(t TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT NULLIF(btrim(regexp_replace(
        upper(public.unaccent('public.unaccent'::regdictionary, coalesce(t, ''))),
        '[^A-Z0-9]+', ' ', 'g')), '')
$$;

-- tipos de logradouro: só removidos quando abrem o nome
CREATE OR REPLACE FUNCTION cwb.tipos_logradouro() RETURNS TEXT[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT ARRAY['R','RUA','AV','AVE','AVENIDA','AL','ALAMEDA','TV','TRV','TRAV','TRAVESSA',
                 'PC','PCA','PRC','PRACA','ROD','RODOVIA','EST','ESTR','ESTRADA','LG','LGO','LARGO',
                 'VD','VIADUTO','VIA','BC','BECO','LAD','LADEIRA','PQ','PRQ','PARQUE','SV','SERVIDAO',
                 'PSG','PASSAGEM','CJ','CONJ','CONJUNTO','LOT','LOTEAMENTO','ACESSO','MARGINAL','CONTORNO']
$$;

-- títulos e palavras de ligação: removidos em qualquer posição
CREATE OR REPLACE FUNCTION cwb.titulos_logradouro() RETURNS TEXT[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT ARRAY['DR','DRA','DOUTOR','DOUTORA','PROF','PROFA','PROFESSOR','PROFESSORA',
                 'ENG','ENGENHEIRO','ENGENHEIRA','GAL','GEN','GENERAL','CEL','CORONEL','MAL','MARECHAL',
                 'PE','PADRE','STA','SANTA','STO','SANTO','SAO','S','CAP','CAPITAO','TEN','TENENTE',
                 'DEP','DEPUTADO','SEN','SENADOR','VER','VEREADOR','PRES','PRESIDENTE','MAJ','MAJOR',
                 'DES','DESEMBARGADOR','COM','COMEND','COMENDADOR','BRIG','BRIGADEIRO','ALM','ALMIRANTE',
                 'MONS','MONSENHOR','FREI','DOM','D','DONA','SGT','SARGENTO','CB','CABO','SD','SOLDADO',
                 'VISC','VISCONDE','BAR','BARAO','CONS','CONSELHEIRO','MIN','MINISTRO','GOV','GOVERNADOR',
                 'PREF','PREFEITO','IR','IRMA','IRMAO','MME','MADRE','N','NS','NSRA','NOSSA','SENHORA',
                 'DE','DA','DO','DAS','DOS','E']
$$;

CREATE OR REPLACE FUNCTION cwb.norm_logradouro(t TEXT) RETURNS TEXT
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    toks TEXT[];
    saida TEXT[] := '{}';
    tk TEXT;
    i INT := 1;
BEGIN
    toks := regexp_split_to_array(cwb.norm_txt(t), ' ');
    IF toks IS NULL OR array_length(toks, 1) IS NULL THEN
        RETURN NULL;
    END IF;
    WHILE i < array_length(toks, 1) AND toks[i] = ANY (cwb.tipos_logradouro()) LOOP
        i := i + 1;
    END LOOP;
    FOR j IN i .. array_length(toks, 1) LOOP
        tk := toks[j];
        IF NOT tk = ANY (cwb.titulos_logradouro()) THEN
            saida := saida || tk;
        END IF;
    END LOOP;
    IF array_length(saida, 1) IS NULL THEN
        RETURN array_to_string(toks[i:], ' ');
    END IF;
    RETURN array_to_string(saida, ' ');
END
$$;

-- número predial: primeiro grupo de dígitos; "S/N", "SN", "0" e vazio viram NULL
CREATE OR REPLACE FUNCTION cwb.norm_numero(t TEXT) RETURNS INTEGER
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT NULLIF(left(substring(coalesce(t, '') FROM '[0-9]+'), 6)::INT, 0)
$$;

CREATE OR REPLACE FUNCTION cwb.norm_cep(t TEXT) RETURNS VARCHAR(8)
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN length(d) = 8 AND d <> '00000000' THEN d END
    FROM (SELECT regexp_replace(coalesce(t, ''), '[^0-9]', '', 'g') AS d) x
$$;
