import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { FileText, LogOut } from "lucide-react";

export const AppHeader = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/");
  };

  return (
    <header className="sticky top-0 z-40 bg-background border-b border-border" data-testid="app-header">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link
          to={user?.role === "admin" ? "/admin" : "/dashboard"}
          className="flex items-center gap-2 text-primary"
          data-testid="header-logo-link"
        >
          <FileText className="h-6 w-6" />
          <span className="font-serif text-xl font-semibold">FiloClinico</span>
        </Link>
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground hidden sm:block" data-testid="header-user-name">
            {user?.name}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={handleLogout}
            className="rounded-full"
            data-testid="logout-button"
          >
            <LogOut className="h-4 w-4 mr-2" />
            Esci
          </Button>
        </div>
      </div>
    </header>
  );
};
