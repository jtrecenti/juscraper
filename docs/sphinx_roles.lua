-- Hands Sphinx roles quartodoc leaves untouched to the interlinks filter.
--
-- quartodoc only rewrites Sphinx roles inside a `See Also` section, and only
-- when the name has no digit (its regex skips InputCJSGTRF3). Anywhere
-- else (summary, parameter and exception descriptions, notes, free-text
-- blocks), Markdown reads :meth:`cjsg` as the plain text ":meth:" glued to the
-- inline code `cjsg`, and the page shows the role verbatim. In Pandoc's AST
-- that is a Str ending in the role, immediately followed by a Code element,
-- with no Space between them; ordinary prose never puts a role-shaped Str
-- right against code, so that adjacency is the signature this filter matches.
--
-- Each match becomes the same empty-text Link quartodoc emits in `See Also`,
-- target ":role:%60name%60" (Pandoc percent-encodes the backticks of a link
-- target, and interlinks only handles targets holding "%60"). interlinks then
-- treats both sections alike: a full path listed in objects.json becomes a
-- link, anything else becomes inline code, with the `~` prefix shortened to
-- the last dotted component. Unlike quartodoc's regex, this match accepts
-- digits in the name, so it also catches the `See Also` roles quartodoc skips.
--
-- :meth: gets one more step, for both kinds of link (the ones built here and
-- the ones quartodoc writes in `See Also`). objects.json lists methods under
-- the role `function`, which interlinks never derives from `meth`, so the role
-- is rewritten. A short name, as in :meth:`cjsg`, means a method of the class
-- the page documents, as in Sphinx; it is qualified with the identifier of the
-- page's level-1 header, which quartodoc sets to the object's full path, and
-- prefixed with `~` so the link text stays the short name. A name interlinks
-- cannot find still becomes inline code.
--
-- Must run after `quarto` and before `interlinks` in docs/_quarto.yml: after
-- `quarto`, so the links it creates do not reach Quarto's table step (see the
-- comment there); before `interlinks`, which resolves them.

-- Last component of the role, as Sphinx's Python domain names it. Restricting
-- to these keeps a word ending in a colon, as in "Default:`x`", out.
local ROLES = {
    attr = true, class = true, const = true, data = true, exc = true,
    func = true, meth = true, mod = true, obj = true,
}

-- Splits "(:py:meth:" into "(" and ":py:meth:"; nil when the Str does not
-- end in a known role. The prefix is whatever punctuation precedes the role.
local function split_role(text)
    local prefix, role = text:match("^(.-)(:[%w_%+%.:]*:)$")
    if role == nil then
        return nil
    end
    local last = role:match(":([%a]+):$")
    if last == nil or not ROLES[last] then
        return nil
    end
    -- the lazy prefix stops at the first colon; a prefix ending in a word
    -- character would mean "foo:meth:", which is not a role
    if prefix:match("[%w_]$") then
        return nil
    end
    return prefix, role
end

-- Full path of the object the page documents, read from the level-1 header
-- that opens it; nil on pages quartodoc did not write, such as index.qmd.
local page_object = nil

-- Rewrites a :meth: target as interlinks can resolve it; other roles pass.
local function method_target(role, name)
    if not role:match(":meth:$") then
        return role, name
    end
    role = role:gsub("meth:$", "function:")
    local bare = name:gsub("^~", "")
    if page_object ~= nil and not bare:find(".", 1, true) then
        name = "~" .. page_object .. "." .. bare
    end
    return role, name
end

local function role_link(role, name)
    role, name = method_target(role, name)
    return pandoc.Link({}, role .. "%60" .. name .. "%60")
end

local function Inlines(inlines)
    local out = pandoc.Inlines({})
    local i = 1
    while i <= #inlines do
        local el = inlines[i]
        local nxt = inlines[i + 1]
        local prefix, role
        if el.t == "Str" and nxt ~= nil and nxt.t == "Code" then
            prefix, role = split_role(el.text)
        end
        if role ~= nil then
            if prefix ~= "" then
                out:insert(pandoc.Str(prefix))
            end
            out:insert(role_link(role, nxt.text))
            i = i + 2
        else
            out:insert(el)
            i = i + 1
        end
    end
    return out
end

-- The empty-text links quartodoc writes in `See Also`.
local function Link(link)
    local role, name = link.target:match("^(:[%w_%+%.:]*:)%%60(.-)%%60$")
    if role == nil or #link.content > 0 or not role:match(":meth:$") then
        return nil
    end
    role, name = method_target(role, name)
    link.target = role .. "%60" .. name .. "%60"
    return link
end

function Pandoc(doc)
    -- quartodoc opens every page it writes with that header; any other first
    -- block means a hand-written page, where short names stay unqualified
    local first = doc.blocks[1]
    if first ~= nil and first.t == "Header" and first.level == 1
        and first.identifier:match("^juscraper%.") then
        page_object = first.identifier
    end
    return doc:walk({ Inlines = Inlines, Link = Link })
end
