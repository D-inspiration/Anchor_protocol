"""Simple query builder for Anchor Protocol."""

class Q:
    """Minimal query builder - AND/OR conditions."""
    
    AND = "AND"
    OR = "OR"
    
    def __init__(self, **kwargs):
        self.conditions = kwargs
        self.connector = self.AND
        self.negated = False
        self.children = []
    
    def __and__(self, other):
        new = Q()
        new.connector = self.AND
        new.children = [self, other]
        return new
    
    def __or__(self, other):
        new = Q()
        new.connector = self.OR
        new.children = [self, other]
        return new
    
    def __invert__(self):
        new = Q()
        new.negated = True
        new.children = [self]
        return new
    
    def to_sql(self, table_alias=''):
        """Convert to SQL WHERE clause and params."""
        parts = []
        params = []
        
        # Direct conditions
        for key, value in self.conditions.items():
            col = f"{table_alias}.{key}" if table_alias else key
            if value is None:
                parts.append(f"{col} IS NULL")
            elif isinstance(value, (list, tuple)):
                placeholders = ','.join('?' * len(value))
                parts.append(f"{col} IN ({placeholders})")
                params.extend(value)
            else:
                parts.append(f"{col} = ?")
                params.append(value)
        
        # Child conditions
        for child in self.children:
            child_sql, child_params = child.to_sql(table_alias)
            if child_sql:
                parts.append(child_sql)
                params.extend(child_params)
        
        if not parts:
            return "", []
        
        sql = f" {self.connector} ".join(f"({p})" for p in parts)
        if self.negated:
            sql = f"NOT ({sql})"
        
        return sql, params
        