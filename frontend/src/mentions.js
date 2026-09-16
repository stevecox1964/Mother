export function mentionRecipient(text, models) {
  const value = text.trimStart();
  if (!value.startsWith("@")) return null;
  const matches = models.flatMap((model) =>
    [model.name, model.id].flatMap((alias) =>
      [alias, `"${alias}"`]
        .filter((label) => {
          const prefix = `@${label}`;
          return (
            value.toLowerCase().startsWith(prefix.toLowerCase()) &&
            (value.length === prefix.length ||
              /[\s:,]/.test(value[prefix.length]))
          );
        })
        .map((label) => ({ model, length: label.length + 1 })),
    ),
  );
  if (!matches.length)
    return { error: "Choose an @model from this project's suggestions." };
  const longest = Math.max(...matches.map((m) => m.length));
  const found = [
    ...new Map(
      matches.filter((m) => m.length === longest).map((m) => [m.model.id, m]),
    ).values(),
  ];
  if (found.length !== 1)
    return {
      error: "This model name is ambiguous. Choose its unique @profile ID.",
    };
  const { model, length } = found[0];
  if (!model.enabled)
    return { error: "This model is disabled. Enable it in Project setup." };
  return { model, empty: !value.slice(length).replace(/^[\s:,]+/, "") };
}
