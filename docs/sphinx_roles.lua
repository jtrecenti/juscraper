-- Hands Sphinx roles outside `See Also` to the interlinks filter.
--
-- quartodoc only rewrites Sphinx roles inside a `See Also` section. Anywhere
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
-- digits in the name, as in InputCJSGTRF3.
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

function Inlines(inlines)
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
            out:insert(pandoc.Link({}, role .. "%60" .. nxt.text .. "%60"))
            i = i + 2
        else
            out:insert(el)
            i = i + 1
        end
    end
    return out
end
