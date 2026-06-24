import { ReactNode, ComponentType } from 'react';

export interface TileProps extends React.HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function Tile({ children, className = '', ...props }: TileProps) {
  return (
    <div
      className={`border border-border rounded-lg bg-card p-4 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export interface TileHeaderProps {
  label: string;
  icon?: ComponentType<{ className?: string }>;
}

export function TileHeader({ label, icon: Icon }: TileHeaderProps) {
  return (
    <div className="flex items-center gap-2">
      {Icon && <Icon className="h-5 w-5 text-muted-foreground" />}
      <h3 className="font-semibold text-sm">{label}</h3>
    </div>
  );
}
